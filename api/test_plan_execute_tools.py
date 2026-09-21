"""§十四 · N15 —— Plan-and-Execute **执行层真调用工具**的回归用例（2026-09-21）。

📌 **本文件守的是那件最容易悄悄回退的事**：
   `execute_single_step()` 曾经**只对 `calculator` 真调用**，其余**全部交给 LLM「模拟执行」** ——
   端点 `/agent/plan_execute` 看起来在跑真工具，**实际只有规划是真的**。

   这种回退**跑一下看不出**（模拟出来的结果也是一段合理文本），
   所以判据必须是**结构性的**：见 `test_execute_single_step_does_not_ask_the_llm`。
"""
import datetime

import pytest


def _step(tool: str) -> dict:
    return {"step": 1, "action": "测试步骤", "tool": tool}


# ===========================================================================
# 🔴 决定性用例：执行时**不许碰 LLM**
# ===========================================================================
def test_execute_single_step_does_not_ask_the_llm(monkeypatch):
    """**执行**单步时不能调 LLM —— 真调用与「请 LLM 模拟执行」的分水岭。

    判据：把 `executor_llm.invoke` 换成**一调就炸**的替身。
      · 真调用 ⇒ 三个工具**照样出结果**（根本不碰 LLM）
      · 旧实现（模拟）⇒ 立刻炸 ⇒ 本用例红

    📌 这是那条「**跑一下看不出**」的回退的**唯一结构性判据**：
       模拟产出的也是一段像样的文本，光比对输出发现不了。
    """
    import plan_execute as P

    class _BoomLLM:
        """一调就炸的假 LLM。⚠️ 不能直接 `setattr` 真 `executor_llm.invoke` ——
        它是 pydantic 模型，`monkeypatch.setattr` 会报 `object has no field "invoke"`。"""

        def invoke(self, *a, **k):
            raise AssertionError(
                "执行单步时调用了 LLM —— 说明又退回「请 LLM 模拟执行」了！"
                "真执行层必须走 MCP 注册表的 handler。"
            )

    monkeypatch.setattr(P, "executor_llm", _BoomLLM())

    assert P.execute_single_step(_step("calculator"), "3*4-5/6", "").startswith("11.1666")
    assert "今天是" in P.execute_single_step(_step("date_today"), "今天", "")
    assert P.execute_single_step(_step("execute_python"), "print(6*7)", "").strip() == "42"


# ===========================================================================
# 真调用返回的是【真结果】，不是"像样的文本"
# ===========================================================================
def test_calculator_returns_the_exact_arithmetic_result():
    """`calculator` 先前就是真调的 —— 这里把它钉住，防止重写时退化成模拟。"""
    import plan_execute as P

    assert P.execute_single_step(_step("calculator"), "2**10", "") == str(2 ** 10)
    # 一个 LLM「模拟」几乎不会算对的式子
    assert P.execute_single_step(_step("calculator"), "123456789*987654321", "") == str(
        123456789 * 987654321
    )


def test_date_today_returns_the_real_today():
    """`date_today` 是**最能区分真假**的一个：
    LLM 并不知道"今天"是哪天（它的知识有截止日），**模拟必错**；真调用必对。
    """
    import plan_execute as P

    out = P.execute_single_step(_step("date_today"), "今天", "")
    today = datetime.date.today()
    assert f"{today.year}年{today.month}月{today.day}日" in out, (
        f"返回的不是今天（{today}）：{out!r} —— 是不是又退化成让 LLM 模拟了？"
    )


def test_execute_python_actually_runs_the_code():
    """`execute_python` 真跑：钉的是**算出来**的那个数，不是"像样的文本"。
    ⚠️ **不能写 `import math`** —— 沙箱里 `__import__` 不在白名单（见下条用例）。
    """
    import plan_execute as P

    code = "print(sum(i * i for i in range(100)))"
    expected = sum(i * i for i in range(100))
    assert P.execute_single_step(_step("execute_python"), code, "").strip() == str(expected)


def test_sandbox_modules_are_injected_not_importable():
    """🔴 **沙箱里【不能 `import`】—— 模块是直接注入全局域的。**

    实测（2026-09-21）：
      · `import math`            → ❌ `ImportError: __import__ not found`
      · 不 import，直接用 `math`  → ✅ `4.0`

    ⚠️ **为什么专门钉这条**：`execute_python` 的工具描述**曾经**写着
      「允许的模块：math, json, …」—— 那会让 LLM 写出 `import math` 然后**必炸**。
      本用例与 `test_tool_description_warns_against_import` 一起，
      把「描述 ↔ 实现」两边都锁住。
    """
    import plan_execute as P

    assert "ImportError" in P.execute_single_step(
        _step("execute_python"), "import math\nprint(math.sqrt(16))", ""
    )
    assert P.execute_single_step(
        _step("execute_python"), "print(math.sqrt(16))", ""
    ).strip() == "4.0"


def test_tool_description_warns_against_import():
    """工具描述（**LLM 读的那份**）必须明说「**不要 `import`**」，否则 LLM 会照惯例写 import。

    📌 这是 §三·A 那一类「**注释说 A、代码做 B**」的同型 —— 但后果更重：
       它直接导致 **LLM 写出来的代码跑不了**（而以前是"模拟执行"，看不出来）。
    """
    from code_executor import execute_python

    desc = execute_python.description or ""
    assert "不要" in desc and "import" in desc, (
        "`execute_python` 的工具描述没提醒 LLM「不要 import」—— "
        "沙箱里 __import__ 不在白名单，LLM 写 `import math` 会直接炸。\n"
        f"当前描述：\n{desc}"
    )


# ===========================================================================
# 参数名从 MCP 注册表【派生】，不手写
# ===========================================================================
def test_tool_arg_field_is_derived_from_the_registry():
    """字段名必须来自工具自己的 `args_schema` —— 手写映射会与注册表漂移
    （这正是 §三·C1「工具清单手工维护必然漂」的同一个根因）。"""
    import plan_execute as P
    from mcp_server import TOOLS

    for t in TOOLS:
        fn = t["func"]
        expected = list(fn.args_schema.model_fields.keys())
        got = P._tool_arg_field(fn.name)
        if len(expected) == 1:
            assert got == expected[0], f"{fn.name}: 派生出 {got!r}，schema 是 {expected}"
        else:
            assert got is None, f"{fn.name}: 多字段工具应当返回 None（不猜参数名）"

    assert P._tool_arg_field("这个工具不存在") is None


def test_execute_single_step_wraps_the_value_into_the_schema_field(monkeypatch):
    """传给 handler 的必须是 `{schema 里的字段名: 值}` —— 键名错了真工具会报缺参。"""
    import plan_execute as P

    seen = {}

    class _FakeHandler:
        def __call__(self, args):
            seen.update(args)
            return "OK"

    monkeypatch.setitem(P._TOOL_HANDLERS, "calculator", _FakeHandler())
    out = P.execute_single_step(_step("calculator"), "1+1", "")

    assert out == "OK"
    assert seen == {"expression": "1+1"}, f"传给 handler 的键不对：{seen}"


# ===========================================================================
# 失败路径：抛异常，不吞成字符串（否则重试机制静默失效）
# ===========================================================================
def test_unknown_tool_raises_instead_of_returning_a_string():
    """⚠️ 必须**抛异常** —— 上游 `execute_step_with_retry` 靠异常触发"重新生成输入再试"。
    吞成错误字符串会让它**看起来在重试、其实没有**。"""
    import plan_execute as P

    with pytest.raises(ValueError, match="未找到工具"):
        P.execute_single_step({"step": 1, "action": "x", "tool": "根本没这个工具"}, "x", "")


def test_tool_exception_propagates(monkeypatch):
    """真工具自己抛错时，也要**透传**给上游的重试逻辑。"""
    import plan_execute as P

    def _explode(args):
        raise RuntimeError("工具内部炸了")

    monkeypatch.setitem(P._TOOL_HANDLERS, "calculator", _explode)
    with pytest.raises(RuntimeError, match="工具内部炸了"):
        P.execute_single_step(_step("calculator"), "1+1", "")


# ===========================================================================
# 代码围栏：LLM 很爱给 execute_python 包 ```，包着会直接语法错
# ===========================================================================
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("```python\nprint(1)\n```", "print(1)"),
        ("```\nprint(1)\n```", "print(1)"),
        ("print(1)", "print(1)"),
        ("  print(1)  ", "print(1)"),
    ],
)
def test_strip_code_fence(raw, expected):
    import plan_execute as P

    assert P._strip_code_fence(raw) == expected


# ===========================================================================
# ③-b · 预算与记账 —— `plan_execute` 以前【完全不查预算、不记账】
# ===========================================================================
def _fake_llm(usage, content="ok"):
    class _R:
        pass

    class _L:
        model_name = "fake-model"

        def invoke(self, messages):
            r = _R()
            r.content = content
            r.usage_metadata = usage
            return r

    return _L()


def test_invoke_llm_raises_budget_exceeded(monkeypatch):
    """预算不足时**必须抛 `BudgetExceededError`** —— 端点据此报 QUOTA_EXCEEDED（而不是漏成 500）。

    🔴 这条守的是：`/agent/plan_execute` **以前根本不查预算** ⇒ 免费用户的每日配额管不到它。
    """
    import plan_execute as P

    monkeypatch.setattr(P, "check_budget_before_call", lambda *a, **k: (False, "预算已用完"))

    called = []
    llm = _fake_llm({"input_tokens": 1, "output_tokens": 1})
    monkeypatch.setattr(llm, "invoke", lambda m: called.append(1))

    with pytest.raises(P.BudgetExceededError, match="预算已用完"):
        P._invoke_llm(llm, [], purpose="plan_execute.plan", user_name="u1")

    assert called == [], "预算不足时**不该**还去调 LLM（钱已经花出去了）"


def test_invoke_llm_records_real_usage(monkeypatch):
    """正常时按 `usage_metadata` 的【真实 token】记账（照 2 代 `/agent/mcp_chat` 的模式）。"""
    import plan_execute as P

    monkeypatch.setattr(P, "check_budget_before_call", lambda *a, **k: (True, "充足"))
    recorded = {}
    monkeypatch.setattr(P, "record_usage", lambda **kw: recorded.update(kw))

    P._invoke_llm(
        _fake_llm({"input_tokens": 123, "output_tokens": 45}),
        [], purpose="plan_execute.quality_check", user_name="u1",
    )

    assert recorded["prompt_tokens"] == 123
    assert recorded["completion_tokens"] == 45
    assert recorded["purpose"] == "plan_execute.quality_check"
    assert recorded["user_name"] == "u1", "记账必须落到【发起人】头上，否则配额管不到他"
    assert recorded["model"] == "fake-model"


def test_invoke_llm_does_not_fabricate_usage(monkeypatch):
    """没有 `usage_metadata` 时**如实不记** —— 不编一个数字塞进账里。"""
    import plan_execute as P

    monkeypatch.setattr(P, "check_budget_before_call", lambda *a, **k: (True, "充足"))
    recorded = []
    monkeypatch.setattr(P, "record_usage", lambda **kw: recorded.append(kw))

    P._invoke_llm(_fake_llm(None), [], purpose="plan_execute.plan", user_name="u1")

    assert recorded == [], "没有真实用量却记了账 —— 那是在【编数字】"


def test_plan_execute_entry_points_accept_user_name():
    """两个入口必须能收 `user_name` —— 否则记账落不到人头上，配额就是摆设。"""
    import inspect

    import plan_execute as P

    for fn in (P.plan_task, P.execute_plan, P.execute_plan_with_replan):
        assert "user_name" in inspect.signature(fn).parameters, (
            f"{fn.__name__} 没有 user_name 形参 ⇒ 记账会落到 'unknown'，配额管不到任何人"
        )


# ===========================================================================
# ③ 的遗留 · LLM 调用自身的超时 + 整条计划的总时长上限
# ===========================================================================
def test_llm_clients_have_explicit_timeouts():
    """三个 LLM 客户端**必须显式设超时** —— 否则吃 openai SDK 默认的 `read=600s`。

    🔴 这条守的是「**③ 只补了工具调用、漏了 LLM 调用**」那半边：
       实测（2026-09-21）三个客户端都是 `timeout=None` ⇒ 吃 SDK 默认
       `connect=5s / read=600s / write=600s`，**且 SDK 还会自己 max_retries=2**
       ⇒ **一次调用最坏等 600 × (1+2) = 30 分钟**；而 `plan_execute` 最坏跑
       「3–7 步 × 每步重试 3 次 × 每步 2 次 LLM 调用」⇒ **理论上能挂几个小时**。

    ⚠️ 这里**断言"非 None"而不是断言具体秒数** —— 秒数是可以调的参数，
       而"**必须显式**"才是要守的性质（回到 SDK 默认 = 回到 10 分钟）。
    """
    import plan_execute as P

    for name in ("planner_llm", "executor_llm", "quality_checker_llm"):
        llm = getattr(P, name)
        assert llm.request_timeout is not None, (
            f"{name} 没设超时 ⇒ 会吃 openai SDK 默认的 read=600s（10 分钟）"
        )
        assert llm.max_retries is not None, (
            f"{name} 的 max_retries 是 None ⇒ 吃 SDK 默认 2 —— 最坏时长不可算"
        )


def test_plan_stops_when_total_budget_exceeded(monkeypatch):
    """**整条计划**要有总时长上限 —— 而且停下来时必须【如实说没跑完】。

    ⚠️ 判据有两层，缺一不可：
      ① 真的停下来了（不是继续跑）
      ② 输出里**明说"结果不完整"** —— 不能让它看起来像正常结束
    """
    import plan_execute as P

    # ⚠️ **不要用 `0`** —— 那是个**边界**不是"已超"：判据是 `elapsed > budget`，
    #    而第一次检查时 `elapsed ≈ 0`（`time.time()` 微秒精度，两次连续调用甚至可能同值）
    #    ⇒ `0 > 0` 为 False ⇒ 第一步照跑。用 `-1` 才是**确定的"已超"状态**。
    monkeypatch.setattr(P, "PLAN_TOTAL_BUDGET_SECONDS", -1)

    called = []
    monkeypatch.setattr(
        P, "execute_step_with_quality_check",
        lambda *a, **k: called.append(1) or "不该被调用",
    )

    out = P.execute_plan_with_replan(
        [{"step": 1, "action": "a", "tool": "calculator", "input": "1+1"},
         {"step": 2, "action": "b", "tool": "calculator", "input": "2+2"}],
        "目标", "u1",
    )

    assert called == [], "总预算已超，却还执行了步骤"
    assert "超过总时长预算" in out, out
    assert "结果不完整" in out, f"停下来时没如实说明结果不完整：{out!r}"
    assert "2 个步骤未执行" in out, f"没报出剩余步骤数：{out!r}"
