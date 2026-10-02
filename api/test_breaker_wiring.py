"""`B11` **接线**回归：每一条真烧钱的链，都要真的问过断路器。

## 为什么需要这个文件（`test_breaker.py` 不管这件事）

那边测的是**断路器本身**对不对（派发 / fail-open / 透传）。
**函数全对但没人调它，等于没有熔断** —— 而且**所有测试照样全绿**。

📌 这是本仓**栽过三次**的同型陷阱（`B7` 之前 · `B10` 本身 · 「门挂在别处就等于没有门」），
   ⇒ 每个「建好函数」的 Task 都配一份 `*_wiring.py`：`test_max_tokens_wiring.py`（`B7`）·
   `test_session_budget_wiring.py`（`B8`）· 本文件（`B11`）。

## 🔴 与 `B8` 的范围【几乎相同、但多一条】

`B11` 的清单 = `B8` 那 **7 条**（`DEC-041` 已逐条实测过的"真调 LLM"链）**+ 1 条**：

| 多出来的这条 | 为什么 `B8` 没收它，`B11` 却必须收 |
|---|---|
| `api_v1.py::benchmark_embedding`（`POST /api/v1/rag/benchmark-embedding`） | 它**真的调 DashScope 的 embedding**（两次 `get_embedding`）⇒ **真花钱**；而且它的签名是 `async def benchmark_embedding(req: QuestionRequest)`，**⛔ 没有 `Depends` 鉴权** ⇒ **可以匿名打**。<br>⚠️ `B8` 是**会话级**上限，需要 `user_name`/`thread_id` —— 这条链**两者都没有**，接不上。<br>✅ `B11` 是**全站**级，`circuit("global:<日期>")` **不需要用户身份** ⇒ 正好是唯一能管住它的那层。 |

⚠️ **已知的近似**：该端点的 embedding 开销**未必**计入 `token_usage_logs`（那是 LLM token 的账）。
   ⇒ 拿 **token** 预算去闸它是**代理指标**，不是精确计量。
   判据：**「全站今天已经超预算了，就别再拿调试端点烧账号了」** —— 这是策略，不是计量。

## ⚠️ 与 `B8` 一样，这 4 条【故意不接】

`/rag/ask` · `/rag/jwt_ask` · `/rag/async_ask` · `/rag/parallel_ask` —— 只查库或纯 mock，
**一分钱不花**。接上去 ⇒ 用户为**没发生**的调用被 429（`DEC-041` 范围表已裁）。
"""
import ast
import pathlib

import pytest

# (文件, 函数名) —— 表就是**权威清单**，与 `test_session_budget_wiring.py::EXPECTED_WIRED` 同性质
EXPECTED_WIRED = [
    # ===== 与 B8 完全相同的 7 条 =====
    ("api_v1_agent.py", "langgraph_chat"),        # POST /agent/langgraph_chat
    ("api_v1_agent.py", "advanced_agent_chat"),   # POST /agent/advanced_chat
    ("api_v1_agent.py", "agent_plan_execute"),    # POST /agent/plan_execute
    ("api_v1_agent.py", "memory_chat"),           # POST /agent/memory_chat
    ("api_v1_agent.py", "mcp_agent_chat"),        # POST /agent/mcp_chat
    ("api_v1_rag.py", "stream_search"),           # POST /rag/stream_search（SSE）
    ("api_v1_rag.py", "agent_websocket"),         # WS   /ws/agent
    # ===== B11 新增：唯一一条【匿名可打且真花钱】的 =====
    ("api_v1.py", "benchmark_embedding"),         # POST /rag/benchmark-embedding
]

# ⚠️ 用 `circuit` 这个【调用名】匹配。全仓已核：`circuit(` 只在 breaker.py 定义，
#    无同名函数 ⇒ 不会误判（⛔ 别改成 `check_global_daily_budget` ——
#    那是被派发的一端，直接调它 = 绕开断路器这一层）。
GUARD = "circuit"
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
def test_endpoint_calls_breaker(filename, func_name):
    """每一条链都必须**真的**调用 `circuit()`。

    ⚠️ 本测试**红了不要删它** —— 它红的意思是"这条链现在对全站熔断**完全不设防**"。
       若你是**故意**要摘掉某条链，先改本文件的 `EXPECTED_WIRED`，**再**动代码。
    """
    tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
    fn = _find_function(tree, func_name)

    assert fn is not None, (
        f"{filename} 里找不到函数 {func_name}() —— 端点被改名/删掉了？"
        "  那要同步改本文件的 EXPECTED_WIRED"
    )
    assert GUARD in _calls_in(fn), (
        f"{filename}:{fn.lineno} 的 {func_name}() **没有**调用 {GUARD}()\n"
        "  ⇒ 这条链不受全站日级熔断约束，而**所有测试照样全绿**（这正是本文件存在的理由）。"
    )


def test_the_four_non_spending_endpoints_stay_unwired():
    """🔴 **反向守卫**：那 4 条【不花钱】的端点，⛔ **不许**被接上断路器。

    **危害方向与上一条相反，但同样是真问题**：它们一分钱不花，
    接上 ⇒ 全站额度用尽时，连**查库**的接口都 429 了 —— **没有任何账单依据**。
    """
    NON_SPENDING = [
        ("api_v1_rag.py", "ask_question"),           # /rag/ask       —— 只查 documents
        ("api_v1_rag.py", "jwt_ask_question"),       # /rag/jwt_ask   —— 只查 documents
        ("api_v1_rag.py", "async_ask_question"),     # /rag/async_ask —— mock
        ("api_v1_rag.py", "parallel_ask_question"),  # /rag/parallel_ask —— mock
    ]
    for filename, func_name in NON_SPENDING:
        tree = ast.parse((_API / filename).read_text(encoding="utf-8"))
        fn = _find_function(tree, func_name)
        assert fn is not None, f"{filename} 里找不到 {func_name}()"
        assert GUARD not in _calls_in(fn), (
            f"{filename}:{fn.lineno} 的 {func_name}() 被接上了断路器，但它**不花钱**：\n"
            "  ⇒ 全站额度用尽时，一个不消耗额度的接口也被 429。"
        )
