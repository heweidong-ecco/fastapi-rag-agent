"""`B8` **接线**回归：7 条真正调 LLM 的对话链，每条都要真的问过会话预算。

## 为什么需要这个文件（`test_session_budget_offline.py` 不管这件事）

那边测的是**函数本身**对不对（数据源 / 窗口 / key / 判定）。
**函数全对但没人调它，等于没有上限** —— 而且**所有测试照样全绿**。

📌 同型先例就在本仓：`docs/复盘/2026-09-16-八个PR跳过了留痕门.md` ——
   「**门挂在别处，就等于没有门**」。Task 1（`B7`）的 `test_max_tokens_wiring.py` 也是为这个才建的。

## ⚠️ 为什么是【这 7 条】（2026-10-01 逐条实测）

只收**真的调 LLM、真的烧 token** 的对话端点。**以下 4 条【故意不在表里】**，因为它们不消耗 token，
接上去是**错的**（会让不花钱的接口占额度甚至被拦）：

| 端点 | 为什么不接 |
|---|---|
| `/rag/ask` | 只 `SELECT content FROM documents`，不调 LLM |
| `/rag/jwt_ask` | 同上 |
| `/rag/async_ask` | `await asyncio.sleep(2)` 后返回假字符串（**mock**） |
| `/rag/parallel_ask` | 同上（调 `async_search`） |

📌 裁定见 `docs/decisions/DEC-041-B8会话上限的窗口与接线范围.md` 备选方案·三
   （⚠️ 本表最初**列错**过 —— 把上面 4 条也列了进去，核实后才剔除）。
"""
import ast
import pathlib

import pytest

# (文件, 函数名) —— 表就是**权威清单**，与 `test_max_tokens_wiring.py` 的 `EXPECTED_ROLES` 同性质
#   ⚠️ 后者 2026-10-02（`①b` Task 5）由 `EXPECTED_MAX_TOKENS` 改名而来。
EXPECTED_WIRED = [
    ("api_v1_agent.py", "langgraph_chat"),        # POST /agent/langgraph_chat
    ("api_v1_agent.py", "advanced_agent_chat"),   # POST /agent/advanced_chat
    ("api_v1_agent.py", "agent_plan_execute"),    # POST /agent/plan_execute
    ("api_v1_agent.py", "memory_chat"),           # POST /agent/memory_chat
    ("api_v1_agent.py", "mcp_agent_chat"),        # POST /agent/mcp_chat
    ("api_v1_rag.py", "stream_search"),           # POST /rag/stream_search（SSE）
    ("api_v1_rag.py", "agent_websocket"),         # WS   /ws/agent
]

GUARD = "check_session_token_budget"
_API = pathlib.Path(__file__).parent


def _calls_in(fn: ast.AST) -> set:
    """函数体里**被调用到的名字**（只看 `Name` / `Attribute`，⛔ 不看注释与字符串）。"""
    names = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        names.add(getattr(f, "id", None) or getattr(f, "attr", None))
    return names


def _find_function(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


@pytest.mark.parametrize("filename,func_name", EXPECTED_WIRED)
def test_endpoint_calls_session_budget(filename, func_name):
    """每一条链都必须**真的**调用 `check_session_token_budget`。

    ⚠️ 本测试**红了不要删它** —— 它红的意思是"这条链现在对会话上限**完全不设防**"。
       若你是**故意**要摘掉某条链（比如它改成纯检索了），
       请先改 `DEC-041` 的范围表，**再**改本文件的 `EXPECTED_WIRED`。
    """
    tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
    fn = _find_function(tree, func_name)

    assert fn is not None, (
        f"{filename} 里找不到函数 {func_name}() —— 端点被改名/删掉了？"
        "  那要同步改本文件的 EXPECTED_WIRED 与 DEC-041 的范围表"
    )
    assert GUARD in _calls_in(fn), (
        f"{filename}:{fn.lineno} 的 {func_name}() **没有**调用 {GUARD}()\n"
        "  ⇒ 这条对话链不受会话上限约束，而**所有测试照样全绿**（这正是本文件存在的理由）。\n"
        "  若是有意移除，先改 `DEC-041` 的范围表。"
    )


def test_the_four_non_llm_endpoints_stay_unwired():
    """🔴 **反向守卫**：那 4 条【不调 LLM】的端点，⛔ **不许**被接上限。

    **危害方向与上一条相反，但同样是真问题**：
    `/rag/ask` / `/rag/jwt_ask` / `/rag/async_ask` / `/rag/parallel_ask` 只查库或纯 mock，
    **一分 token 都不花**。接上会话上限 ⇒ 用户**白白被扣额度甚至被 429**，
    而账单上根本没有对应的消耗 —— 这是**向用户收费却没有服务**。

    📌 本表最初正是**列错**了这 4 条（核实端点实现时才剔除）⇒ 本条把它钉住。
    """
    NON_LLM = [
        ("api_v1_rag.py", "ask_question"),           # /rag/ask       —— 只查 documents
        ("api_v1_rag.py", "jwt_ask_question"),       # /rag/jwt_ask   —— 只查 documents
        ("api_v1_rag.py", "async_ask_question"),     # /rag/async_ask —— mock
        ("api_v1_rag.py", "parallel_ask_question"),  # /rag/parallel_ask —— mock
    ]
    for filename, func_name in NON_LLM:
        tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
        fn = _find_function(tree, func_name)
        assert fn is not None, f"{filename} 里找不到 {func_name}()"
        assert GUARD not in _calls_in(fn), (
            f"{filename}:{fn.lineno} 的 {func_name}() 被接上了会话上限，但它**不调 LLM**：\n"
            "  ⇒ 用户会为一次**没有发生**的 LLM 调用被扣额度。"
        )
