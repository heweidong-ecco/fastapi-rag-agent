"""`*_impl.py` 两个「纯 stdlib 内核」的单元测试（§三·D2 · 2026-09-20）

背景：`code_executor_impl.py` / `simple_tools_impl.py` 的 docstring 都声称
「**可脱离 langchain 单测**」—— 而这个**能力是真的**（实测两个模块只 import 标准库：
一个是 `datetime`，另一个是 `io` + `contextlib`），**只是从来没人用过它**
（全仓唯一引用者是各自的 `@tool` 外壳，没有任何测试在跑）。

⚠️ 所以这组用例的意义**不是"发现了 bug"**，而是两件正事：

1. **兑现那句声明** —— 否则它就是一句**没被验证过的话**（本仓最防的那类）。
2. **锁住那次重构的收益** —— 「⑥ 切开点 3」把沙箱逻辑抽成纯 stdlib，目的就是让它可测；
   但**没有测试，下次改动静悄悄把 langchain 依赖塞回去，没人会发现**。
   ⇒ 下面 `test_impl_modules_do_not_import_langchain` 就是那条**结构性锁**。

📌 这组用例**刻意跑得飞快**（不碰 Redis / DB / LLM），因为那两个模块本来就只依赖标准库 ——
   如果哪天它开始需要 fixture，说明**声明已经被破坏**了。
"""
import importlib
import re
import sys
import types


# ===========================================================================
# 结构性锁：两个模块必须【只依赖标准库】
# ===========================================================================
def test_impl_modules_do_not_import_langchain():
    """`*_impl.py` 一旦 import 了 langchain，那条「可脱离 langchain 单测」的声明就**失效了**。

    ⚠️ 这不是形式检查：`simple_tools.py` 与 `code_executor.py` 的**模块层**都有
       `from langchain_core.tools import tool` ⇒ 它们**没法**在只有标准库的环境里导入。
       当初抽出 `_impl` 就是为了解决这个 —— **所以"不反向依赖"是那笔重构的全部意义所在**。
    """
    for name in ("simple_tools_impl", "code_executor_impl"):
        mod = importlib.import_module(name)
        tree = __import__("ast").parse(open(mod.__file__, encoding="utf-8").read())
        imported = set()
        for node in __import__("ast").walk(tree):
            if isinstance(node, __import__("ast").Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, __import__("ast").ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        banned = {m for m in imported if m.startswith("langchain") or m.startswith("langgraph")}
        assert not banned, f"{name} 不应依赖 langchain 系（那会让「可脱离 langchain 单测」失效）：{banned}"

        # 反向依赖也要禁：_impl 不该 import 自己的 @tool 外壳
        shell = "simple_tools" if name.startswith("simple") else "code_executor"
        assert shell not in imported, f"{name} 不该反向 import {shell}（依赖方向必须是单向的）"


# ===========================================================================
# simple_tools_impl
# ===========================================================================
def test_calculator_impl_evaluates_and_reports_errors():
    from simple_tools_impl import calculator_impl

    assert calculator_impl("3*4") == "12"
    assert calculator_impl("7/2") == "3.5"

    # ⚠️ 出错时**返回字符串**而不是抛异常 —— 这是给 LLM 当工具用的，不能让它炸
    out = calculator_impl("1/0")
    assert out.startswith("计算错误:"), f"除零应当返回'计算错误:…'，实际：{out!r}"
    assert "division by zero" in out


def test_date_today_impl_returns_a_readable_date():
    from simple_tools_impl import date_today_impl

    out = date_today_impl()
    assert out.startswith("今天是"), out
    assert re.search(r"星期[一二三四五六日]", out), out


# ===========================================================================
# code_executor_impl —— 沙箱
# ===========================================================================
# 沙箱里**不该有**的东西（`ALLOWED_BUILTINS` 里确实没有它们）
_DANGEROUS_BUILTINS = (
    "open", "eval", "exec", "compile", "__import__",
    "input", "globals", "locals", "getattr", "setattr", "vars",
)


def test_sandbox_globals_exclude_dangerous_builtins():
    """`create_safe_globals()` 给出的 `__builtins__` 里，**不能有**能逃逸沙箱的那些名字。

    ⚠️ 这条是这组用例里**唯一带安全含义**的 —— 它把"沙箱到底挡了什么"变成**可执行的事实**，
       而不是 docstring 里一句话。
    """
    from code_executor_impl import create_safe_globals

    g = create_safe_globals()
    assert isinstance(g.get("__builtins__"), dict), "`__builtins__` 应当是被裁剪过的 dict"

    present = sorted(n for n in _DANGEROUS_BUILTINS if n in g["__builtins__"])
    assert not present, f"沙箱的 __builtins__ 里不该出现这些：{present}"


def test_sandbox_actually_blocks_open_at_runtime():
    """光看白名单不够 —— **真跑一段**试图读文件的代码，必须失败。

    ⚠️ 用 `/etc/hosts`（任何机器上都有、且非敏感）当探针：**只看"会不会被挡"**，不读内容。
    """
    from code_executor_impl import execute_python_impl

    out = execute_python_impl("print(open('/etc/hosts').read())")
    assert "NameError" in out, f"沙箱应当让 `open` 不存在（NameError），实际返回：{out!r}"


def test_execute_python_impl_runs_code_and_captures_stdout():
    from code_executor_impl import execute_python_impl

    assert execute_python_impl("print(1+1)").strip() == "2"
    assert execute_python_impl("print('a'); print('b')").strip() == "a\nb"


def test_execute_python_impl_handles_no_output_and_errors():
    from code_executor_impl import execute_python_impl

    assert execute_python_impl("x = 1").strip() == "代码执行成功，但无输出内容。"

    # ⚠️ 用 `1/0`（**由解释器自己抛** ZeroDivisionError）来测错误路径。
    #    ⛔ **不能**用 `raise ValueError('boom')` —— 沙箱的 `ALLOWED_BUILTINS` 里
    #    **没有任何异常类** ⇒ 那样写会先 `NameError: name 'ValueError' is not defined`，
    #    测到的就不是"用户代码抛错"而是"沙箱白名单太窄"（那是另一回事，见下一条用例）。
    out = execute_python_impl("1/0")
    assert out.startswith("代码执行出错:"), out
    assert "ZeroDivisionError" in out, out


def test_sandbox_whitelist_has_no_exception_classes():
    """⚠️ **记录一条沙箱限制**（不是断言它"对"）—— 白名单里**没有异常类**。

    ⇒ 被执行的代码**不能**写 `try: … except ValueError: …`，也不能 `raise ValueError(…)`
      —— 两者都会先撞 `NameError: name 'ValueError' is not defined`。

    🔴 **为什么要专门测它**：这是一条**会实际影响"LLM 写的代码能不能跑"**的限制
       （异常处理是最常见的 Python 写法之一），而它**从代码上看不出来**
       （`ALLOWED_BUILTINS` 那一长串里"没有异常类"是**沉默的**）。
       ⇒ 把它变成一条**会红的断言**：哪天有人把异常类加进白名单，这条用例会提醒
         **去更新这条记录**，而不是让文档悄悄过期。

    📌 已登记为 `docs/待办登记…` §三·**N17**（**未修，待裁**：要不要放开异常类）。
    """
    from code_executor_impl import create_safe_globals

    builtins_ = create_safe_globals()["__builtins__"]
    for exc in ("Exception", "ValueError", "TypeError", "KeyError", "ZeroDivisionError"):
        assert exc not in builtins_, (
            f"沙箱白名单里现在**有** {exc} 了 —— 这说明限制已放开，"
            "请更新本用例与登记文件 §三·N17 的记录（不要只是把断言删掉）。"
        )


def test_execute_python_impl_truncates_long_output():
    """输出超长必须**截断并写明** —— 否则会把 LLM 的上下文冲掉。"""
    from code_executor_impl import execute_python_impl, MAX_OUTPUT_LENGTH

    out = execute_python_impl(f"print('x' * {MAX_OUTPUT_LENGTH * 2})")
    assert out.endswith("... (输出过长，已截断)"), out[-80:]
    assert len(out) < MAX_OUTPUT_LENGTH * 2, "截断后不该还是原长度"


def test_execute_python_impl_rejects_natural_language_requests():
    """它只执行**已写好的代码**，不接受"需求描述" —— 那条拒绝逻辑必须真的生效。

    📌 这是"工具描述"与"实现"一致性的用例：`code_executor.py` 的 docstring 对 LLM 说
       「只能执行已编写好的代码，不能生成代码」，这里验证**实现真的这么做了**。
    """
    from code_executor_impl import execute_python_impl

    out = execute_python_impl("帮我写一段计算斐波那契的代码")
    assert "不是可执行的 Python 代码" in out, out
