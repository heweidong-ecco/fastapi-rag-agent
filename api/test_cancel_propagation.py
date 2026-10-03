"""`③` Task 5（`B2`）—— **服务端 cancel 传播到上游**。

## 这个文件测的是「最难假完成」的那一件事

硬门 C 的三条判据里，前两条（前端停 / 日志有 cancel）**都能在"其实没停"的情况下成立** ——
前端停可能只是前端不再显示，而后端**还在烧钱**。
⇒ 所以这里**一条都不测前端**，只测**服务端与上游之间**发生了什么。

## 判据为什么钉在 ASGI 层（⛔ 不是"自己造一个取消"）

**取消是谁发起的？** 不是我们的代码 —— 是 **Starlette 收到 `http.disconnect` 后
取消 `stream_response` 任务**。uvicorn 实测报 `spec_version: "2.3"` ⇒ 走的是
`create_collapsing_task_group` + `listen_for_disconnect` 那条路。

⇒ 如果测试自己 `task.cancel()`，那测的是**我假想的取消**，不是**线上真会发生的那次取消**。
本文件直接把 `StreamingResponse` 当成 ASGI app 跑一遍（`await resp(scope, receive, send)`），
`receive` 在**第 N 帧发出之后**回 `http.disconnect` —— 与真服务器走的是**同一段代码**。

## 🔴 假上游为什么是「手动迭代器」而不是 async generator

写了 `async def` + `yield` 的假上游，**红不出来**：`asyncio.run()` 收尾时会
`shutdown_asyncgens()`，把没人关的异步生成器**顺手关掉** ⇒ `finally` 照跑 ⇒
**"被我们关了"和"被事件循环收尾关了"长得一模一样**（实测：改前 5 条里有 3 条因此假绿）。

⇒ 假上游实现 `__aiter__` / `__anext__` / `aclose`，**故意不是 async generator**。
这样 `closed` 为真就**只能**是**我们的代码调了 `aclose()`**。

## ⚠️ 两条链的观测对象不一样，别混

| 链 | 落在哪 | 数什么 |
|---|---|---|
| Prometheus | `api/metrics.py` | ✅ **本轮新加的 `stream_cancelled_total`** |
| PG（`token_usage_logs`） | `api/token_tracker.py` | ⚠️ **流式生成阶段不记账** ⇒ 拿它当判据**看不到任何东西**（本任务踩过） |

📄 裁定与理由 ⇒ `docs/decisions/DEC-052-取消传播的观测对象与上游改异步.md`
"""

import asyncio
import contextlib
import json

from langchain_core.messages import AIMessageChunk
from prometheus_client import REGISTRY

import api_v1_agent as agent_mod
import api_v1_rag as rag_mod
from schemas import QuestionRequest

RAG_ENDPOINT = "rag_stream_search"
AGENT_ENDPOINT = "agent_langgraph_chat_stream"

# 断开发生在**第几帧之后** —— 取 2 是为了留出一帧的余量，
# 免得把"正在途中的那一块"误判成"断开后还在拉"。
DISCONNECT_AFTER = 2
# 断开后最多还允许出现这么多次拉取（在途那一块）。
TOLERANCE = 2


# ==================== ASGI 层的"客户端断开" ====================


def _body_chunks(sent):
    """只数 `http.response.body` 的**非空**帧（`start` 与收尾的空帧不算）。"""
    return [m["body"] for m in sent
            if m["type"] == "http.response.body" and m.get("body")]


def _drive_asgi_until_disconnect(resp, *, after_chunks):
    """把 `StreamingResponse` 当 ASGI app 跑，并在**第 `after_chunks` 帧之后**断开客户端。

    ⚠️ `spec_version` 必须写 **"2.3"** —— 那是 uvicorn 实测报的版本。
       换成 "2.4" 会走 Starlette 另一条分支（`except OSError: raise ClientDisconnect`），
       **取消就不会送进生成器** ⇒ 测出来的东西和线上不是一回事。
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "method": "POST",
        "path": "/under-test",
        "headers": [],
    }
    sent = []
    disconnected = asyncio.Event()

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if len(_body_chunks(sent)) >= after_chunks:
            disconnected.set()

    async def go():
        await resp(scope, receive, send)

    asyncio.run(go())
    return sent


# ==================== 假上游（手动迭代器 · 见文件头） ====================


class _AsyncSpyStream:
    """**故意不是 async generator** —— 否则会被 `shutdown_asyncgens()` 关掉，测不出真因。"""

    def __init__(self, owner, item_factory, first_delay=None):
        self.owner = owner
        self.item_factory = item_factory
        self.first_delay = first_delay
        self.i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.i >= self.owner.cap:
            raise StopAsyncIteration
        self.i += 1
        self.owner.pulled += 1
        # ⚠️ 第一块的等待时长可调：`B3` 要测「**一块都还没生成**就断了」，
        #    而那是**竞态** —— 首块等太短，断开还没送到，测试就变成掷骰子。
        delay = self.first_delay if self.i == 1 and self.first_delay else 0.01
        await asyncio.sleep(delay)  # 给取消一个**真的 await 点**（没有它就取消不进来）
        return self.item_factory()

    async def aclose(self):
        self.owner.closed = True


class _SyncSpyStream:
    """旧的同步上游 —— **留在假对象里，只是为了让 RED 的理由是"没关流"而不是"没有 .stream"**。"""

    def __init__(self, owner, item_factory):
        self.owner = owner
        self.item_factory = item_factory
        self.i = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.i >= self.owner.cap:
            raise StopIteration
        self.i += 1
        self.owner.pulled += 1
        return self.item_factory()

    def close(self):
        self.owner.closed = True


class _SpyRagLLM:
    """假的流式 LLM：**一直吐**（直到被关掉），记录被拉了几块、有没有被关、走的哪条路。

    ⚠️ `cap` 是**安全阀** —— 取消没生效时，测试应当**断言失败**，⛔ 不是挂住。
    """

    def __init__(self, cap=40, first_delay=None):
        self.cap = cap
        self.first_delay = first_delay
        self.pulled = 0
        self.closed = False
        self.astream_calls = []
        self.stream_calls = []  # ⛔ 换异步之后必须保持为空

    def astream(self, messages):
        self.astream_calls.append(messages)
        return _AsyncSpyStream(
            self, lambda: AIMessageChunk(content="字"), first_delay=self.first_delay
        )

    def stream(self, messages):
        self.stream_calls.append(messages)
        return _SyncSpyStream(self, lambda: AIMessageChunk(content="字"))


class _SpyGraph:
    """假的图：与 `test_agent_sse._FakeGraph` 同款，**额外记「流有没有被关」**。"""

    def __init__(self, cap=40):
        self.cap = cap
        self.pulled = 0
        self.closed = False
        self.aget_state_calls = []

    def astream(self, payload, config, stream_mode):
        return _AsyncSpyStream(
            self, lambda: (AIMessageChunk(content="字"), {"langgraph_node": "agent"})
        )

    async def aget_state(self, config):
        self.aget_state_calls.append(config)
        return type("S", (), {"values": {"messages": []}})


# ==================== 驱动两条端点 ====================


class _FakeConn:
    def cursor(self):
        return _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeCursor:
    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _call_rag_stream(monkeypatch, llm, history=None, **kw):
    """直接调端点函数，把**所有**外部依赖短路 —— 本文件测的是取消，⛔ 不是检索/预算/认证。

    ⚠️ 传 `history=[]` ⇒ 把写入历史的调用**记下来**（`B3` 的观测对象）；
       不传 ⇒ 照旧短路掉（其余用例不关心历史）。
    """
    monkeypatch.setattr(rag_mod, "get_chat_history", lambda user: [])
    monkeypatch.setattr(rag_mod, "check_session_token_budget", lambda *a, **k: (True, ""))
    monkeypatch.setattr(rag_mod, "circuit", lambda *a, **k: (True, ""))
    monkeypatch.setattr(rag_mod, "get_embedding", lambda text: [0.0] * 8)
    monkeypatch.setattr(rag_mod, "get_llm_stream", lambda: llm)
    monkeypatch.setattr(rag_mod, "get_db", lambda: _FakeConn())
    if history is None:
        monkeypatch.setattr(rag_mod, "append_chat_history", lambda *a, **k: None)
    else:
        monkeypatch.setattr(
            rag_mod, "append_chat_history", lambda *a, **k: history.append(a)
        )
    kw.setdefault("thread_id", "t-cancel")
    kw.setdefault("user_name", "tester")
    req = QuestionRequest(question=kw.pop("question", "你好"))
    return asyncio.run(rag_mod.stream_search(req, **kw))


def _call_agent_stream(monkeypatch, graph, **kw):
    monkeypatch.setattr(agent_mod, "agent_graph", graph)
    monkeypatch.setattr(agent_mod, "check_session_token_budget", lambda *a, **k: (True, ""))
    monkeypatch.setattr(agent_mod, "circuit", lambda *a, **k: (True, ""))
    monkeypatch.setattr(agent_mod, "register", lambda *a, **k: None)
    monkeypatch.setattr(agent_mod, "resolve", lambda *a, **k: None)
    kw.setdefault("thread_id", "t-cancel")
    kw.setdefault("user_name", "tester")
    kw.setdefault("question", "你好")
    return asyncio.run(agent_mod.langgraph_chat_stream(**kw))


@contextlib.contextmanager
def _capture_logs():
    """抓 loguru 的日志 —— 判据第一条就是「**日志里有 cancel 事件**」，得能打印出来。"""
    from loguru import logger
    lines = []
    handler_id = logger.add(lambda msg: lines.append(str(msg)), level="INFO")
    try:
        yield lines
    finally:
        logger.remove(handler_id)


def _metric(endpoint):
    return REGISTRY.get_sample_value("stream_cancelled_total", {"endpoint": endpoint}) or 0.0


# ==================== RAG 端（`/rag/stream_search`） ====================


def test_rag_closes_upstream_when_client_disconnects(monkeypatch):
    """🔴🔴 **本任务的核心断言**：客户端断开后，**上游 HTTP 流必须被真的关掉**。

    ⚠️ 关不掉 = 上游继续生成、**继续计费** —— 而前端看起来一切正常（它只是不显示了）。
       这正是硬门 C 标"最容易假完成"的原因。
    """
    llm = _SpyRagLLM()
    resp = _call_rag_stream(monkeypatch, llm)
    _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    assert llm.pulled >= DISCONNECT_AFTER, f"根本没流起来（只拉了 {llm.pulled} 块）⇒ 本断言无意义"
    assert llm.closed, "客户端断开后上游流**没有被关** ⇒ 上游还在跑、还在烧钱"


def test_rag_stops_pulling_upstream_after_disconnect(monkeypatch):
    """断开之后**不再向上游要下一块** —— 关流是果，不再拉取才是"真的停了"。"""
    llm = _SpyRagLLM(cap=40)
    resp = _call_rag_stream(monkeypatch, llm)
    _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    assert llm.pulled >= DISCONNECT_AFTER, f"根本没流起来（只拉了 {llm.pulled} 块）⇒ 本断言无意义"
    assert llm.pulled <= DISCONNECT_AFTER + TOLERANCE, f"断开后仍拉了 {llm.pulled} 块 ⇒ 上游没停"


def test_rag_uses_async_upstream(monkeypatch):
    """上游必须是**异步**的（`astream`）—— 同步 `for` 会阻塞事件循环，取消只能等"下一块到达"。"""
    llm = _SpyRagLLM(cap=3)
    resp = _call_rag_stream(monkeypatch, llm)
    _drive_asgi_until_disconnect(resp, after_chunks=99)

    assert llm.astream_calls, "端点没有走异步上游"
    assert not llm.stream_calls, "端点仍在走同步 `stream()` ⇒ 事件循环会被阻塞"


def test_rag_sends_nothing_after_disconnect(monkeypatch):
    """🔴 **取消之后不许再发帧** —— 旧实现在 `except CancelledError` 里还 `yield "data: [DONE]"`。

    ⚠️ 那不仅无意义（接收方已经走了），还会让"已取消"和"正常收尾"在**帧层面长得一样**。
    """
    llm = _SpyRagLLM()
    resp = _call_rag_stream(monkeypatch, llm)
    sent = _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    bodies = _body_chunks(sent)
    assert len(bodies) >= DISCONNECT_AFTER, f"根本没流出帧（只有 {len(bodies)} 帧）⇒ 本断言无意义"
    assert not any(b"[DONE]" in b for b in bodies), f"取消后还发了帧：{bodies}"
    assert len(bodies) <= DISCONNECT_AFTER + TOLERANCE, f"断开后仍在发：{len(bodies)} 帧"


def test_rag_records_cancel_event(monkeypatch):
    """判据①②：**日志里有 cancel 事件** + Prometheus 计数 +1（Grafana 里看得见）。"""
    llm = _SpyRagLLM()
    before = _metric(RAG_ENDPOINT)
    resp = _call_rag_stream(monkeypatch, llm)
    with _capture_logs() as lines:
        _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    assert _metric(RAG_ENDPOINT) == before + 1, "取消没有计数 ⇒ Grafana 上看不到它"
    assert any("cancel" in line.lower() or "断开" in line for line in lines), f"日志里没有取消事件：{lines}"


def test_rag_normal_completion_is_not_counted_as_cancel(monkeypatch):
    """⛔ **反面**：正常跑完不算取消 —— 否则这个指标就是个恒增的假信号。"""
    llm = _SpyRagLLM(cap=3)
    before = _metric(RAG_ENDPOINT)
    resp = _call_rag_stream(monkeypatch, llm)
    sent = _drive_asgi_until_disconnect(resp, after_chunks=99)  # 永不触发断开

    bodies = _body_chunks(sent)
    assert bodies[-1].strip() == b"data: [DONE]", f"正常收尾的末帧不对：{bodies[-1]!r}"
    assert llm.closed, "正常跑完也要关流（否则连接泄漏）"
    assert _metric(RAG_ENDPOINT) == before, "正常收尾被记成了取消"


# ============ RAG 端 · `③` Task 6（`B3`）：中断时那半截答案怎么办 ============
#
# 核出来的事实（`docs/decisions/DEC-053`）：取消时 `collected_parts` 是**直接丢**的，
# 而且不是"决定"，是"碰巧" —— `append_chat_history` 写在循环之后，取消在它之前 `raise`。
# ⇒ 这里把「丢」改成「存」，并把**存的形态**钉死。


def _seen_content(sent):
    """客户端**真的收到**的内容 —— 用于核对"存进历史的就是这一段"（⛔ 不是"存了点什么"）。"""
    parts = []
    for b in _body_chunks(sent):
        text = b.decode()
        if not text.startswith("data: {"):
            continue  # `data: [DONE]` 之类
        parts.append(json.loads(text[len("data: "):])["content"])
    return "".join(parts)


def test_rag_persists_partial_answer_when_cancelled(monkeypatch):
    """🔴 `B3` 核心：客户端断开后，**已经生成的那半截要进历史**（⛔ 不是直接丢）。

    ⚠️ 为什么非存不可：`api_v1_rag.py:667` 那行注释早就写了这个意图 ——
       「如果有停止当前消息先放历史……真停止按钮的调用（**使它支持历史补偿**）」。
       取消时丢掉 ⇒ 用户那问句**也一起丢**（它跟答案写在同一段代码里）。
    """
    llm = _SpyRagLLM()
    hist = []
    resp = _call_rag_stream(monkeypatch, llm, history=hist, question="中断也要留痕")
    sent = _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    seen = _seen_content(sent)
    assert seen, "根本没流出内容 ⇒ 本断言无意义"
    assert [h[1] for h in hist] == ["user", "assistant"], (
        f"中断后历史应**成对**写入 user+assistant，实际 {hist}"
    )
    assert hist[0][2] == "中断也要留痕", f"用户那问句没存对：{hist[0]}"
    assert hist[1][2] == seen + rag_mod.INTERRUPTED_SUFFIX, (
        f"存进历史的不是客户端看到的那半截（或缺中断标记）：{hist[1][2]!r}"
    )


def test_rag_full_answer_is_saved_without_interrupt_marker(monkeypatch):
    """⛔ **反面**：正常跑完 ⇒ 存**完整**答案，⛔ **不许**带中断标记。

    否则下一轮 prompt 会把一个好好的回答当成"被截断的"，模型的行为跟着变。
    """
    llm = _SpyRagLLM(cap=3)
    hist = []
    resp = _call_rag_stream(monkeypatch, llm, history=hist, question="完整的一问")
    _drive_asgi_until_disconnect(resp, after_chunks=99)  # 永不触发断开

    assert [h[1] for h in hist] == ["user", "assistant"], f"正常收尾的历史不对：{hist}"
    assert hist[1][2] == "字" * 3, f"正常收尾存的不是完整答案：{hist[1][2]!r}"
    assert rag_mod.INTERRUPTED_SUFFIX not in hist[1][2], "完整答案被误标成了中断"


def test_rag_cancel_before_any_chunk_saves_nothing(monkeypatch):
    """边界：**一块都没生成**就断了 ⇒ 什么都不写。

    写一条空的助手消息只会污染下一轮 prompt（模型看到"回答是空的"）。
    ⚠️ 首块延迟调大是为了让"断开送到"与"首块产出"的**竞态**稳定倒向我们要测的那一边。
    """
    llm = _SpyRagLLM(first_delay=0.3)
    hist = []
    resp = _call_rag_stream(monkeypatch, llm, history=hist, question="还没开始就断了")
    _drive_asgi_until_disconnect(resp, after_chunks=0)

    assert hist == [], f"没生成任何内容却写了历史：{hist}"


# ==================== Agent 端（`/agent/langgraph_chat/stream`） ====================


def test_agent_closes_graph_stream_when_client_disconnects(monkeypatch):
    """Agent 端同一条要求 —— `DEC-050` 自己点了「新加的流式路由也没有 cancel 处理」。"""
    graph = _SpyGraph()
    resp = _call_agent_stream(monkeypatch, graph)
    _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    assert graph.pulled >= DISCONNECT_AFTER, f"根本没流起来（只拉了 {graph.pulled} 块）⇒ 本断言无意义"
    assert graph.closed, "客户端断开后，图的流**没有被关** ⇒ 图会继续跑完"
    assert graph.pulled <= DISCONNECT_AFTER + TOLERANCE, f"断开后仍拉了 {graph.pulled} 块"


def test_agent_sends_nothing_after_disconnect(monkeypatch):
    graph = _SpyGraph()
    resp = _call_agent_stream(monkeypatch, graph)
    sent = _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    bodies = _body_chunks(sent)
    assert len(bodies) >= DISCONNECT_AFTER, f"根本没流出帧（只有 {len(bodies)} 帧）⇒ 本断言无意义"
    assert not any(b"[DONE]" in b for b in bodies), f"取消后还发了帧：{bodies}"


def test_agent_records_cancel_event(monkeypatch):
    graph = _SpyGraph()
    before = _metric(AGENT_ENDPOINT)
    resp = _call_agent_stream(monkeypatch, graph)
    with _capture_logs() as lines:
        _drive_asgi_until_disconnect(resp, after_chunks=DISCONNECT_AFTER)

    assert _metric(AGENT_ENDPOINT) == before + 1
    assert any("cancel" in line.lower() or "断开" in line for line in lines), f"日志里没有取消事件：{lines}"


def test_agent_normal_completion_is_not_counted_as_cancel(monkeypatch):
    """反面：正常跑完 ⇒ 末帧是汇总帧 + `[DONE]`，**且不计取消**。"""
    graph = _SpyGraph(cap=3)
    before = _metric(AGENT_ENDPOINT)
    resp = _call_agent_stream(monkeypatch, graph)
    sent = _drive_asgi_until_disconnect(resp, after_chunks=99)

    bodies = [b.decode() if isinstance(b, bytes) else b for b in _body_chunks(sent)]
    assert bodies[-1].strip() == "data: [DONE]", f"末帧不是 [DONE]：{bodies[-1]!r}"
    summary = json.loads(bodies[-2][len("data: "):])
    assert summary["status"] == "answered", f"汇总帧不对：{summary}"
    assert _metric(AGENT_ENDPOINT) == before, "正常收尾被记成了取消"
