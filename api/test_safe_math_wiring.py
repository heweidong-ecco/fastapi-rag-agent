"""接线守卫：`eval(expression)` 那 5 处**真的**收口到 `safe_math` 了吗？

**为什么单开一个文件**（本仓的老毛病）："写好了" ≠ "接上了"。
`safe_math.py` 本身测得再绿，只要有一个调用点还留着 `eval`，那条路照样是 RCE。
📄 同族守卫 ⇒ `api/test_approval_trigger.py` 的姊妹篇 `api/test_pending_approvals_wiring.py`

**两道，覆盖面不同**（⛔ 不是重复）：

| 闸 | 覆盖 | 挡什么 |
|---|---|---|
| **行为验证** | 4 处（能离线调起来的） | 🔴 最强的一道：**喂真实恶意表达式，验副作用没发生** —— 断言"返回了错误字符串"**不够**，旧代码也返回错误字符串 |
| **AST 静态** | 5 处（含 `tools_with_cache`） | "还留着 `eval` 调用" / "没把入口指向 `calculate`" |

⚠️ **`tools_with_cache` 只进静态那道**：它被 `@cached_tool` 包着 ⇒ 调一次就要连 Redis，
   放进离线套件会让 CI 依赖外部服务。而它在生产里**本就不可达** ——
   ⚠️ **2026-10-07 更新**：原先这里写的是「`api_v1.py:36` 导入了但全文件只用这一次」。
   那天清 `T6` 存量（段 A · `2bae0bb`）把 `api_v1.py` 里那行 `from tools_with_cache import calculator`
   **删了** ⇒ **`api_v1.py` 那个行号现在指向一段注释，⛔ 不再成立**。
   现状更强：**全仓没有任何文件导入它**（判据 ⇒ `grep -rn --include='*.py' "tools_with_cache" api/`
   ⇒ 只剩它自己那行 `from tool_cache import cached_tool`）。
   ⚠️ **但【静态那道仍必须留着】** —— 模块本身还在仓里（`T6`「先挂起」），
   哪天有人把它重新接回某个路由 ⇒ 这一条要能当场红。
⇒ 它的安全性由静态那条 + 代码本身（`return calculate(...)`）共同保证，**这里如实写明，不假装它也验了行为**。
"""

import ast
import importlib
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent


# ===========================================================================
# 零、**唯一的**检测函数 —— 两条闸都调它，⛔ 不许各写一份（那正是漂移的来源）
# ===========================================================================
def eval_name_offenders(tree: ast.AST) -> list[int]:
    """返回**所有「裸名 `eval`」**出现的行号 —— ⛔ 不是"所有 `eval(...)` 调用"。

    🔴 **2026-10-04 修（`DEC-066`）：原判据只抓 `ast.Call` 且 `func` 是裸名 `eval`**，
    于是这一行**两条闸都看不见**：

        result = await asyncio.to_thread(eval, expression)      # api_v1_rag.py:801

    `eval` 是**实参**，不是被调用的目标 —— `ast.Call` 的 `func` 是 `asyncio.to_thread`
    ⇒ 旧判据返回**空**，而**命令真的跑了**（实测：返回值 `'0'`，`touch` 的文件真被创建）。

    ⇒ **改成「只要这个名字被读出来就报」**，与它的**调用形状无关**：
      · `eval(x)`                ✅ 抓到（`ast.Name` 一定在）
      · `to_thread(eval, x)`     ✅ 抓到 —— **旧判据漏的就是这个**
      · `f = eval` / `getattr(m, "eval")` 之类 ✅ 一并抓到

    ⚠️ **⛔ 不会误伤 `redis_client.eval(...)`**（`api/rate_limiter.py` 真家伙）——
       它的 `eval` 是 `ast.Attribute.attr`，**不是** `ast.Name`。

    ⚠️ **改判据时要看它能不能红**（本仓两条教训）：这次改完**先跑**，
       红在 `api_v1_rag.py:801` 才算数 —— 判据纪律见 `api/agent_graph.py` 同名注释 / `DEC-061`。
    """
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "eval"
    )


# ===========================================================================
# 一、行为验证：喂恶意表达式，验"没被执行"
# ===========================================================================
#: (模块名, 入口名) —— 入口名不同是因为 `simple_tools_impl` 那份叫 `calculator_impl`。
OFFLINE_SITES = [
    ("agent_graph", "calculator"),
    ("agent_checkpointer", "calculator"),
    ("agent_graph_advanced_learning", "calculator"),
    ("simple_tools_impl", "calculator_impl"),
]


def _entry_point(module_name: str, attr: str):
    """取到**底下那个真函数**。

    ⚠️ langchain 的 `@tool` 会把函数换成 `StructuredTool` ⇒ 不 `.func` 的话，
       拿到的是工具对象，`fn("1+1")` 会走成"把字符串当 config"，报一个看不出原因的错。
    """
    obj = getattr(importlib.import_module(module_name), attr)
    return getattr(obj, "func", obj)


@pytest.mark.parametrize(
    "module_name,attr", OFFLINE_SITES, ids=[f"{m}.{a}" for m, a in OFFLINE_SITES]
)
def test_site_still_does_arithmetic(module_name, attr):
    """⛔ 收口不许把功能一起收掉：正常算式结果不变。"""
    fn = _entry_point(module_name, attr)

    assert fn("6*7") == "42"
    assert fn("7/2") == "3.5"
    assert fn("1/0").startswith("计算错误:")


@pytest.mark.parametrize(
    "module_name,attr", OFFLINE_SITES, ids=[f"{m}.{a}" for m, a in OFFLINE_SITES]
)
def test_site_does_not_execute_the_expression(module_name, attr, tmp_path):
    """🔴 **本文件最要紧的一条**：`eval` 没了没有，就看**命令有没有真的跑**。

    ⚠️ 只断言返回值是不够的 —— 🔴 **改前实测：它返回的是 `'0'`**（`system()` 的返回值被
       `str()` 成了 `"0"`）⇒ 命令**执行成功**，而**模型收到的是一条正常的"答案是 0"**。
       ⇒ 唯一的判据是**副作用**：那个文件**必须没被创建**。
    """
    marker = tmp_path / "pwned_by_eval"
    fn = _entry_point(module_name, attr)

    out = fn(f"__import__('os').system('touch {marker}')")

    assert out.startswith("计算错误:"), f"应当被拒，实际：{out!r}"
    assert not marker.exists(), (
        f"🔴 {module_name}.{attr} 把表达式**执行**了 —— `eval` 还留在里面"
    )


@pytest.mark.parametrize(
    "module_name,attr", OFFLINE_SITES, ids=[f"{m}.{a}" for m, a in OFFLINE_SITES]
)
def test_site_cannot_read_a_file(module_name, attr, tmp_path):
    """换一种逃逸形状再验一遍（⛔ 别只堵一种 payload 就以为堵住了）。

    ⚠️ **文件必须真的存在** —— 否则 `open()` 抛 `FileNotFoundError`，改前的 `eval`
       也会返回 `计算错误: …` ⇒ 这条就变成"改前就绿"的假测试了。
       ⇒ 判据是**内容没有被读出来**：结果里不许出现 `TOP_SECRET`。
    """
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET_abc123", encoding="utf-8")
    fn = _entry_point(module_name, attr)

    out = fn(f"open({str(secret)!r}).read()")

    assert out.startswith("计算错误:"), f"应当被拒，实际：{out!r}"
    assert "TOP_SECRET_abc123" not in out, f"🔴 文件内容被读出来了：{out!r}"


# ===========================================================================
# 二、AST 静态：5 处都不许再出现 `eval(...)`，且都要指向 `calculate`
# ===========================================================================
#: 全部 5 处 —— ⚠️ **这份名单是"收口的定义"**：将来再复制一份 `calculator`，
#:    要把它加进来（⛔ 别让它成为第 6 个漏网的）。
ALL_SITES = OFFLINE_SITES + [("tools_with_cache", "calculator")]


def _site_files():
    return [(f"api/{name}.py", API_DIR / f"{name}.py") for name, _ in ALL_SITES]


@pytest.mark.parametrize("label,path", _site_files(), ids=[p for p, _ in _site_files()])
def test_no_eval_call_remains(label, path):
    """⛔ 用 AST 而**不是 grep**：注释里也写着 `eval(expression)` 这几个字，
    正则会把说明文字的命中当成违规（本仓栽过：见 `docs/复盘/2026-09-21-拿动作成功当结果正确.md`）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = eval_name_offenders(tree)

    assert not offenders, f"🔴 {label} 里还有裸 `eval` 的引用，行号：{offenders}"


@pytest.mark.parametrize("label,path", _site_files(), ids=[p for p, _ in _site_files()])
def test_site_delegates_to_safe_math(label, path):
    """正向那条：光"没有 eval"还不够 —— 得**确实调用了** `calculate`。

    ⚠️ 只查"调了 `calculate`"，不规定 `from … import calculate` 还是 `safe_math.calculate(...)`
       —— 那是实现细节，钉死只会让下次重构白改一遍测试。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    delegates = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "calculate")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "calculate")
        )
    ]

    assert delegates, f"🔴 {label} 没有调用 `safe_math.calculate` —— 入口没指过去"


# ===========================================================================
# 三、名单自身别放过期了
# ===========================================================================
def test_no_other_module_defines_an_eval_based_calculator():
    """防止"第 n 份拷贝"：全仓扫一遍，谁引用裸名 `eval` 就当违规。

    ⚠️ 扫的是**整个 `api/`**（不只是上面那 5 个文件）—— 上面那 5 个是"已知的"，
       这条管的是"**将来又冒出来的**"。本仓的拷贝文化是真的：这一份就被复制了 5 次。

    🔴 **2026-10-04（`DEC-066`）：这条闸原先【有形盲区】** —— 判据是 `ast.Call` 且 `func` 是裸名
       `eval` ⇒ `asyncio.to_thread(eval, expression)`（`api_v1_rag.py:801`）**它抓不到**，
       而那一处**真的在执行任意代码**（匿名 WS `/ws/agent` 可达）。⇒ 改用 `eval_name_offenders()`。
    """
    offenders = []
    for path in sorted(API_DIR.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [f"{path.name}:{n}" for n in eval_name_offenders(tree)]

    assert not offenders, (
        "🔴 全仓还有裸名 `eval` —— 每多一处，就是一个未收口的任意代码执行面："
        f"{offenders}"
    )
