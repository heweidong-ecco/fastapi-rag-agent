"""Agent 三线的回归测试（对应 2026-09-20 的 demo 就绪度探测）

背景：把 API 真起来逐个打，查出**三条 Agent 路径全断**，而 RAG 那条线完好。
三条**没有一条是业务逻辑错** —— 全是「**依赖漂移**」：装上的版本比代码写作时新。

| # | 位置 | 根因（实测） |
|---|---|---|
| a | `memory_store.py:55` | mem0 **2.0.20** 的 `search` 签名是 `(query, *, top_k=20, filters=None, …)` —— **不收 `user_id`、`limit` 已改名 `top_k`**。线上报 `ValueError: Top-level entity parameters frozenset({'user_id'}) are not supported` |
| b | `agent_graph_advanced.py:110` | **`mcp 1.30.0` 的 `stdio_client` 是 `@asynccontextmanager`** ⇒ 返回 `_AsyncGeneratorContextManager`，**只能用 `async with`，不能 `await`**。线上报 `object _AsyncGeneratorContextManager can't be used in 'await' expression` |
| c | `api_v1_agent.py:51` | 图带 `interrupt_before=["approval"]`，停在审批点时**最后一条消息是"只带工具调用、无文字"的 AIMessage**，端点照搬 `.content` ⇒ **返回 200 + 空答案，且不告诉调用方"正在等审批"** |

⚠️ 这些测试**都用"复刻真实依赖契约的替身"**，不是断言 mock 被调用过：
   替身会**在参数不对时抛错**（照抄线上那条异常的触发条件）——
   所以"生产代码被改回错写法"就会让它红。
"""
import asyncio
import contextlib
import os

import pytest


# ===========================================================================
# (a) memory_store：必须按 mem0 2.x 的签名调用
# ===========================================================================
def test_search_user_memory_matches_mem0_2x_signature(monkeypatch):
    """mem0 2.0.20 只收 `filters=` + `top_k=`；传 `user_id=`/`limit=` 会抛 ValueError。

    这是**线上真实发生的**那条异常（见模块 docstring 表 a）。
    """
    import memory_store

    captured = {}

    class _Mem0Stub:
        """复刻 mem0 2.0.20 的真实契约：旧参数一律拒绝。"""

        def search(self, query, **kwargs):
            bad = {"user_id", "limit"} & set(kwargs)
            if bad:
                raise ValueError(
                    "Top-level entity parameters frozenset({'user_id'}) are not supported "
                    "in search(). Use filters={'user_id': '...'} instead."
                )
            captured.update(kwargs)
            # ⚠️ **真实**形状:`{"results": [...]}` —— mem0 2.x 的 search() 返回 **dict**，
            #    不是 list。第一版测试里我写成了 `[{"memory": …}]`（我以为的形状），
            #    于是"修好了"是假的 —— 线上照样 500（`TypeError: string indices
            #    must be integers`，因为遍历 dict 拿到的是键）。
            return {"results": [{"memory": "用户偏好：用表格回答"}]}

    monkeypatch.setattr(memory_store, "mem0_client", _Mem0Stub())

    out = memory_store.search_user_memory("u1", "我的偏好", top_k=3)

    assert out == ["用户偏好：用表格回答"]
    assert captured.get("filters") == {"user_id": "u1"}, "必须用 filters= 传 user_id"
    assert captured.get("top_k") == 3, "limit= 已改名为 top_k="


def test_search_user_memory_empty_still_returns_list(monkeypatch):
    """没有记忆时返回空列表（不是 None）—— 调用方靠它决定是否注入。"""
    import memory_store

    class _Empty:
        def search(self, query, **kwargs):
            return {"results": []}   # 真实形状：空也是 {"results": []}

    monkeypatch.setattr(memory_store, "mem0_client", _Empty())
    assert memory_store.search_user_memory("u1", "任意") == []


# ===========================================================================
# (b) MCP 会话：stdio_client 是 async context manager，不能 await
# ===========================================================================
def _install_mcp_fakes(monkeypatch, m, events):
    """给 MCP 客户端装一套会记录生命周期事件的替身。"""

    @contextlib.asynccontextmanager
    async def _fake_stdio(server_params):
        events.append("stdio:enter")
        try:
            yield ("READ_STREAM", "WRITE_STREAM")
        finally:
            events.append("stdio:exit")

    class _FakeSession:
        def __init__(self, read, write):
            pass

        async def __aenter__(self):
            events.append("session:enter")
            return self

        async def __aexit__(self, *exc):
            events.append("session:exit")
            return False

        async def initialize(self):
            events.append("initialize")

        async def call_tool(self, name, arguments):
            events.append(f"call_tool:{name}")

            class _Content:
                text = "42"

            class _Result:
                content = [_Content()]

            return _Result()

    monkeypatch.setattr(m, "stdio_client", _fake_stdio)
    monkeypatch.setattr(m, "ClientSession", _FakeSession)


def test_call_mcp_tool_keeps_session_lifecycle_inside_one_task(monkeypatch):
    """B2：会话必须在**当前 task 内**开 → 用 → 关，`call_mcp_tool` 返回时已关闭。

    🔴 为什么不池化（这是 2026-09-20 实测撞出来的）:
      `stdio_client` 基于 **anyio**，其 cancel scope 要求「**进入与退出在同一个 task**」。
      池化的生命周期天然跨 task（启动 task 建 · 请求 task 用 · 归还 task 关）⇒
      实测报 `RuntimeError: Attempted to exit cancel scope in a different task
      than it was entered in` —— 而且它会让**应用启动直接失败**
      （`Application startup failed. Exiting.`）。
      ⚠️ 这比原来的 bug 更糟：原来是"应用能跑、只是 MCP 健康检查挂"。

    反向保护：这条断言同时钉住"**不许把会话漏出去**"——一旦有人改回池化/全局单例，
    事件序列里就会出现"返回时 session 还没 exit"，用例立刻红。
    """
    import agent_graph_advanced as m

    events = []
    _install_mcp_fakes(monkeypatch, m, events)

    out = asyncio.run(m.call_mcp_tool("calculator", {"expression": "6*7"}))

    assert out == "42"
    assert events == [
        "stdio:enter", "session:enter", "initialize",
        "call_tool:calculator", "session:exit", "stdio:exit",
    ], f"生命周期不对（嵌套/关闭时机）：{events}"


def test_mcp_server_path_does_not_depend_on_cwd(monkeypatch, tmp_path):
    """MCP server 的路径必须锚在**模块自身位置**，不能是相对 CWD 的相对路径。

    🔴 2026-09-20 实测（这是"传输层修好了健康检查还是全红"的答案）:
      本仓文档起服务的姿势是 `cd api && uvicorn main:app`，而路径写的是
      `"api/mcp_server.py"` ⇒ 从 `api/` 看是 `api/api/mcp_server.py` —— **不存在**
      ⇒ MCP 子进程起不来 ⇒ 6 个工具全 unhealthy（报 `ExceptionGroup:
      unhandled errors in a TaskGroup`，子异常被 tool_health 的 except 吞掉了）。

      对照实测（同一次调用，只换 cwd）:
        · cwd = 仓库根 → `2`（成功）
        · cwd = `api/` → TaskGroup 异常

    ⇒ 本用例 `chdir` 到一个**完全无关的临时目录**，钉住"与 CWD 无关"。
    """
    import agent_graph_advanced as m

    seen = {}

    class _Params:
        def __init__(self, command=None, args=None):
            seen["args"] = args

    @contextlib.asynccontextmanager
    async def _fake_stdio(server_params):
        yield ("r", "w")

    class _FakeSession:
        def __init__(self, r, w):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def initialize(self):
            pass

        async def call_tool(self, name, arguments):
            class _C:
                text = "ok"

            class _R:
                content = [_C()]

            return _R()

    monkeypatch.setattr(m, "StdioServerParameters", _Params)
    monkeypatch.setattr(m, "stdio_client", _fake_stdio)
    monkeypatch.setattr(m, "ClientSession", _FakeSession)

    monkeypatch.chdir(tmp_path)  # ← 换到完全无关的目录
    asyncio.run(m.call_mcp_tool("calculator", {"expression": "1+1"}))

    script = seen["args"][0]
    assert os.path.isabs(script), f"MCP server 路径必须是绝对路径，实际 {script!r}"
    assert os.path.isfile(script), f"MCP server 路径必须指向真实文件，实际 {script!r}"


def test_get_mcp_tools_also_keeps_lifecycle_inside_one_task(monkeypatch):
    """同上，`get_mcp_tools`（`/agent/mcp_tools_dynamic` 走它）也必须自开自关。"""
    import agent_graph_advanced as m

    events = []

    @contextlib.asynccontextmanager
    async def _fake_stdio(server_params):
        events.append("stdio:enter")
        try:
            yield ("r", "w")
        finally:
            events.append("stdio:exit")

    class _FakeSession:
        def __init__(self, r, w):
            pass

        async def __aenter__(self):
            events.append("session:enter")
            return self

        async def __aexit__(self, *e):
            events.append("session:exit")
            return False

        async def initialize(self):
            events.append("initialize")

        async def list_tools(self):
            events.append("list_tools")
            return "TOOLS"

    monkeypatch.setattr(m, "stdio_client", _fake_stdio)
    monkeypatch.setattr(m, "ClientSession", _FakeSession)

    assert asyncio.run(m.get_mcp_tools()) == "TOOLS"
    assert events == ["stdio:enter", "session:enter", "initialize", "list_tools",
                      "session:exit", "stdio:exit"], events


def test_mcp_server_command_uses_current_interpreter(monkeypatch):
    """MCP 子进程必须用**当前解释器**(venv 的 python)。

    裸 `"python"` 会落到系统 python —— 它**没有本仓依赖**，MCP server 起不来。
    """
    import sys

    import agent_graph_advanced as m

    seen = {}

    class _Params:
        def __init__(self, command=None, args=None):
            seen["command"] = command
            seen["args"] = args

    @contextlib.asynccontextmanager
    async def _fake_stdio(server_params):
        yield ("r", "w")

    class _FakeSession:
        def __init__(self, r, w):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def initialize(self):
            pass

        async def call_tool(self, name, arguments):
            class _Content:
                text = "ok"

            class _Result:
                content = [_Content()]

            return _Result()

    monkeypatch.setattr(m, "StdioServerParameters", _Params)
    monkeypatch.setattr(m, "stdio_client", _fake_stdio)
    monkeypatch.setattr(m, "ClientSession", _FakeSession)

    asyncio.run(m.call_mcp_tool("calculator", {"expression": "1+1"}))

    assert seen["command"] == sys.executable, (
        f"MCP 子进程应用当前解释器 {sys.executable}，实际是 {seen['command']!r}"
    )


# ===========================================================================
# (d) mcp_tool_factory：handler 必须把 arguments 字典【原样】交给 invoke()
# ===========================================================================
def test_mcp_tool_handler_passes_dict_to_invoke():
    """🔴 2026-09-20：原实现 `tool_func.invoke(tool_func.args_schema(**arguments))`
    把 **pydantic 实例**喂给 `StructuredTool.invoke()`，而它要的是 **dict** ⇒

        TypeError: calculator() missing 1 required positional argument: 'expression'

    实测对比（同一个真工具）:
      · `calculator.invoke({"expression":"1+1"})`        → ✅ `'2'`
      · `calculator.invoke(args_schema(**{...}))`        → ❌ TypeError

    ⚠️ 后果被放大：健康检查的判据是「结果里含『**工具调用失败**』⇒ unhealthy」
       ⇒ 这个 bug 让 **6 个工具全标红**，**与传输层是否修好无关**。

    ⚠️ 用**真实**的 `@tool`(langchain)，不用 mock —— 这里要验的正是"我们和
       langchain 的契约对不对"，mock 掉 langchain 就把要验的东西验没了。
    """
    from langchain_core.tools import tool

    import mcp_tool_factory as f

    @tool
    def probe(x: str) -> str:
        """probe 工具（测试用）"""
        return f"got:{x}"

    handler = f.create_mcp_tool_handler(probe)

    # ⚠️ 处理器保持**同步** —— 理由见 test_mcp_server_call_tool_offloads_sync_handler。
    assert not asyncio.iscoroutinefunction(handler)
    assert handler({"x": "hello"}) == "got:hello"


def test_mcp_server_call_tool_offloads_sync_handler(monkeypatch):
    """把同步工具**丢出事件循环**这件事，必须发生在 **async 边界**（`mcp_server.call_tool`）。

    背景（两条都要满足，缺一条都不行）:
      · MCP server（`mcp_server.py:71` 的 `call_tool`）**是 asyncio 服务** ⇒ 同步工具
        直接在它的处理器里跑 ⇒ 同步 Playwright 报
        `It looks like you are using Playwright Sync API inside the asyncio loop.`
      · 但**不能在工厂里把 handler 改成 async** —— 处理器有**第三个调用方**：
        `agent_graph_advanced_learning.py:230` 在**同步**节点里 `result = handler(tool_args)`，
        拿到 coroutine 后 `str(result)` 会写成 `<coroutine object …>`（实测）
        ⇒ 三代 REACT 分支的工具调用**静默失效**。

    ⇒ **正确的落点是在 async 边界处 offload**（`await asyncio.to_thread(handler, …)`），
      处理器本身保持同步 ⇒ 三个调用方都不用改。

    🔴 这一条是"修一条路径时必须问：同一个形状还有别的入口吗"的**第四次**实例 ——
       前三次见 DEC-017 §六。
    """
    import mcp_server as ms

    seen = {}

    def _sync_handler(arguments):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return "OFFLOADED_OK"

    monkeypatch.setitem(ms.TOOL_HANDLERS, "probe", _sync_handler)

    out = asyncio.run(ms.call_tool("probe", {}))

    assert out[0].text == "OFFLOADED_OK"
    assert seen["on_loop"] is False, (
        "同步工具不能在事件循环所在线程里执行 —— 必须在 async 边界处丢到线程里"
    )



# ===========================================================================
# (e) get_llm_with_mcp_tools：mcp 1.30 的 list_tools() 返回 ListToolsResult
# ===========================================================================
def test_get_llm_with_mcp_tools_unpacks_list_tools_result(monkeypatch):
    """`list_tools()` 返回的是 **`ListToolsResult`**（列表在 `.tools`），不是列表本身。

    🔴 实测（2026-09-20）:原实现 `for mcp_tool in tools:` 直接遍历结果对象 ⇒
       pydantic 模型迭代出的是 **(key, value) 元组** ⇒
       `AttributeError: 'tuple' object has no attribute 'name'`
       ⇒ `/agent/mcp_chat`（三代）**500**。

    ⚠️ 用**真实的** mcp 类型构造，不用自造假对象 —— 要验的就是"我们和 mcp 的契约对不对"，
       自造一个"我以为长这样"的假对象，就把要验的东西验没了（本 PR 已经栽过一次：
       mem0 的返回形状我就是这么验错的）。
    """
    from mcp.types import ListToolsResult, Tool

    import agent_graph_advanced as m

    captured = {}

    class _FakeLLM:
        """⚠️ 整个替换 `llm`，而不是 patch 它的方法 ——
        `ChatOpenAI` 是 pydantic 模型，直接 setattr 会抛
        `ValueError: "ChatOpenAI" object has no field "bind_tools"`（我第一版就这么错的，
        那会让用例**因错误的理由红**）。"""

        def bind_tools(self, tools):
            captured["tools"] = tools
            return "BOUND_LLM"

    monkeypatch.setattr(m, "llm", _FakeLLM())

    async def _fake_get_mcp_tools():
        return ListToolsResult(tools=[
            Tool(name="calculator", description="算数", inputSchema={"type": "object"}),
            Tool(name="date_today", description="日期", inputSchema={"type": "object"}),
        ])

    monkeypatch.setattr(m, "get_mcp_tools", _fake_get_mcp_tools)

    assert asyncio.run(m.get_llm_with_mcp_tools()) == "BOUND_LLM"
    assert [t["name"] for t in captured["tools"]] == ["calculator", "date_today"]


# ===========================================================================
# (f) 同步 Playwright 不能在事件循环所在线程里跑
# ===========================================================================
def test_fetch_webpage_is_not_invoked_on_the_event_loop(client, auth_headers, monkeypatch):
    """🔴 实测（2026-09-20）:`playwright._impl._errors.Error: It looks like you are
    using Playwright Sync API inside the asyncio loop.`（`browser_tools.py:13`）

    ⇒ 端点必须把**同步**工具调用丢到线程里（`asyncio.to_thread`）。
    ⚠️ 不能把 `browser_tools` 改成 async —— 它同时被 **MCP server 的同步路径**调用
       （`create_mcp_tool_handler` 里是同步 `tool_func.invoke`）。

    本用例的判据：替身在被调用时检查**当前线程有没有正在跑的事件循环**。
    """
    import asyncio as aio

    import api_v1_agent

    seen = {}

    class _Stub:
        def invoke(self, arguments):
            try:
                aio.get_running_loop()
                seen["on_loop"] = True
            except RuntimeError:
                seen["on_loop"] = False
            return "FAKE_HTML"

    monkeypatch.setattr(api_v1_agent, "fetch_webpage", _Stub())
    r = client.post("/api/v1/agent/fetch_webpage?url=https://example.com",
                    headers=auth_headers)

    assert r.status_code == 200
    assert seen["on_loop"] is False, (
        "同步 Playwright 不能在事件循环所在线程里执行 —— 必须丢到线程里"
    )


def test_screenshot_webpage_is_not_invoked_on_the_event_loop(client, auth_headers, monkeypatch):
    """同上（两个端点都要修 —— 防止只改一个）。"""
    import asyncio as aio

    import api_v1_agent

    seen = {}

    class _Stub:
        def invoke(self, arguments):
            try:
                aio.get_running_loop()
                seen["on_loop"] = True
            except RuntimeError:
                seen["on_loop"] = False
            return "FAKE_PNG_PATH"

    monkeypatch.setattr(api_v1_agent, "screenshot_webpage", _Stub())
    r = client.post("/api/v1/agent/screenshot_webpage?url=https://example.com",
                    headers=auth_headers)

    assert r.status_code == 200
    assert seen["on_loop"] is False, (
        "同步 Playwright 不能在事件循环所在线程里执行 —— 必须丢到线程里"
    )


# ===========================================================================
# (c) /agent/langgraph_chat：等待审批时必须说出来，不能返回空答案
# ===========================================================================
def test_stopped_at_approval_is_reported_not_silently_empty():
    """停在审批点 ⇒ `status='pending_approval'` + 待批工具调用。

    旧行为：`answer` 直接取最后一条消息的 `.content`，而那条是**空**的 ⇒ 调用方收到
    200 + `answer: ""`，**看不出是在等审批**（明明有 `/agent/approve` 配套）。
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from api_v1_agent import summarize_agent_result

    stopped = {
        "messages": [
            HumanMessage(content="请计算 6*7"),
            AIMessage(
                content="",  # ← 关键：只带工具调用，没有文字
                tool_calls=[{"name": "calculator", "args": {"expression": "6*7"},
                             "id": "call_1", "type": "tool_call"}],
            ),
        ]
    }
    out = summarize_agent_result(stopped)

    assert out["status"] == "pending_approval"
    assert [t["name"] for t in out["pending_tool_calls"]] == ["calculator"]
    assert out.get("answer", "") == "", "等待审批时不该伪造答案"


def test_stopped_at_approval_also_when_the_model_wrote_text_first():
    """⚠️ 反向漏洞：模型**既写文字又调工具**时，同样是在等审批。

    真实 LLM 常见这种形态（"我来帮你算一下。" + tool_calls）。原判据写成
    `if tool_calls and not content:` ⇒ 这种形态被判成 `answered`，
    **调用方照样不知道要去 `/agent/approve`** —— 原缺陷原样保留。

    ⚠️ 判据只需看 `tool_calls`：图的接线是 `agent → (approval) → tools`，
       **只要有 tool_calls 就一定停在审批点**；而 ToolMessage **没有 `tool_calls` 属性**，
       本来就不会误报（见下一条用例）。
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from api_v1_agent import summarize_agent_result

    stopped = {
        "messages": [
            HumanMessage(content="6*7=?"),
            AIMessage(content="我来帮你算一下。",
                      tool_calls=[{"name": "calculator", "args": {"expression": "6*7"},
                                   "id": "c1", "type": "tool_call"}]),
        ]
    }
    out = summarize_agent_result(stopped)

    assert out["status"] == "pending_approval"
    assert [t["name"] for t in out["pending_tool_calls"]] == ["calculator"]


def test_react_tool_list_has_no_duplicate_names():
    """REACT 子图绑定的工具列表**不能有重名** —— LLM 会直接拒收。

    🔴 实测（2026-09-20）:模块级 `agent_graph_advanced_learning.tools` 在第 47-51 行
       已列了 `fetch_webpage` / `fetch_webpage_html` / `screenshot_webpage`，
       紧接着第 54 行又 `tools.extend([fetch_webpage, fetch_webpage_html])`
       ⇒ **两个工具各出现两次** ⇒ `llm_react.bind_tools(tools)` 发给 DeepSeek 时被拒：
       `openai.BadRequestError: 400 - {'error': {'message': 'Tool names must be unique.'}}`
       ⇒ **3 代 Agent 的 REACT 分支 100% 500**。

    ⚠️ 它此前**测不出来**，因为 `/agent/advanced_chat` 会先在 mem0 那一步 500（bug 1），
       根本走不到 REACT 分支 —— **修好 bug 1 才把它暴露出来**。
       📌 这也是"真把 API 起来逐个打"比"只跑单测"更能发现问题的一个实例。
    """
    import agent_graph_advanced_learning as L

    names = [t.name for t in L.tools]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"REACT 工具列表有重名（LLM 会拒收）：{dupes}"


def test_react_subgraph_sets_final_output(monkeypatch):
    """REACT 子图必须把最终答案落成 `final_output`。

    🔴 实测（2026-09-20）:该子图只有 `agent` 与 `tools` 两个节点，**没有任何节点写
       `final_output`**，而端点读的是 `result.get("final_output", "处理完成")`
       ⇒ **走 REACT 意图时永远返回占位串「处理完成」**（其余四个子图都写了）。

    ⚠️ 用**替身 LLM**（替换 `ChatOpenAI`）驱动，不真调模型：
       模型返回一条**不带 tool_calls** 的消息 ⇒ `should_continue` 直接 END。
    """
    from langchain_core.messages import AIMessage, HumanMessage

    import agent_graph_advanced_learning as L

    class _Bound:
        def invoke(self, messages):
            return AIMessage(content="三步计划是：先学语法，再写小项目，最后读源码。")

    class _FakeLLM:
        def __init__(self, **kwargs):
            pass

        def bind_tools(self, tools):
            return _Bound()

    monkeypatch.setattr(L, "ChatOpenAI", _FakeLLM)

    graph = L.create_react_subgraph()
    out = graph.invoke({"messages": [HumanMessage(content="帮我规划学习路线")]})

    assert out.get("final_output") == "三步计划是：先学语法，再写小项目，最后读源码。", (
        "REACT 子图没写 final_output ⇒ 端点只会返回占位串「处理完成」"
    )


def test_mcp_tools_dynamic_handles_list_tools_result(client, auth_headers, monkeypatch):
    """`/agent/mcp_tools_dynamic` 也必须解 `.tools` —— 与 bug 7 是**同一个 bug 的第二个入口**。

    🔴 实测（2026-09-20）:`get_mcp_tools()` 返回 `ListToolsResult`，而该端点写的是
       `for t in tools` + `len(tools)` ⇒ `AttributeError: 'tuple' object has no attribute
       'name'` ⇒ **该路由 100% 500**。

    ⚠️ 这是"修一条路径时必须问：同一个形状还有别的入口吗"的**第五次**实例 ——
       `get_mcp_tools` 全仓只有**两个**调用方，改了一个漏了另一个，grep 一次就能发现。
    """
    from mcp.types import ListToolsResult, Tool

    import api_v1_agent

    async def _fake_get_mcp_tools():
        return ListToolsResult(tools=[
            Tool(name="calculator", description="算数", inputSchema={"type": "object"}),
            Tool(name="date_today", description="日期", inputSchema={"type": "object"}),
        ])

    monkeypatch.setattr(api_v1_agent, "get_mcp_tools", _fake_get_mcp_tools)

    r = client.get("/api/v1/agent/mcp_tools_dynamic", headers=auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["name"] for t in body["tools"]] == ["calculator", "date_today"]
    assert body["total"] == 2


def test_completed_run_returns_the_answer_normally():
    """正常跑完（最后一条有文字）⇒ 照旧返回答案，状态为 answered。"""
    from langchain_core.messages import AIMessage, HumanMessage

    from api_v1_agent import summarize_agent_result

    done = {"messages": [HumanMessage(content="6*7=?"), AIMessage(content="42")]}
    out = summarize_agent_result(done)

    assert out["status"] == "answered"
    assert out["answer"] == "42"
    assert "pending_tool_calls" not in out


def test_plain_tool_message_is_not_mistaken_for_approval():
    """⚠️ 反向用例：最后一条是 ToolMessage（工具已执行完）**不算**待审批。

    没有这条，把"最后一条没有文字"一律判成待审批的实现也能让上面两条过 ——
    而那会把"工具刚跑完、正要生成最终答案"的正常中途态误报成待审批。
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from api_v1_agent import summarize_agent_result

    mid = {
        "messages": [
            HumanMessage(content="6*7=?"),
            AIMessage(content="", tool_calls=[{"name": "calculator", "args": {},
                                               "id": "c1", "type": "tool_call"}]),
            ToolMessage(content="42", tool_call_id="c1"),
        ]
    }
    out = summarize_agent_result(mid)

    assert out["status"] != "pending_approval", "工具已执行完，不是待审批"
