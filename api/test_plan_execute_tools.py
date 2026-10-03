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
# 🔴 「降级」不许把失败原因吃掉 —— 否则「炸了」与「真跑出来」长得一样
# ===========================================================================
def test_downgraded_step_keeps_the_real_reason(monkeypatch):
    """工具的**降级分支**必须留下真实失败原因，不能只剩一句编好的兜底文案。

    ⚠️ **判据为什么是"那个原因串在不在"，而不是"输出像不像失败"**：
       兜底文案「工具 X 当前不可用，使用备用策略生成结果。」**读起来像【有意降级】**，
       而它实际是 `except: pass` **吞掉的一个异常** —— **跑一下看不出**。
       只有断言**真实原因**（`工具内部炸了`）在里面，才能把这两者分开。

    📌 **同一个洞的第三面**：`execute_single_step` 的 docstring（`:562`）明文写
       「**失败一律【抛异常】，不吞成错误字符串** —— 上游两条路都是靠异常工作的」，
       **并且点名了就是这个降级分支** —— 而**那个分支自己正是反面**。
       （另两面：`test_unknown_tool_raises_instead_of_returning_a_string` ·
         `test_tool_exception_propagates`）

    驱动方式（不碰真 LLM）：
      让每一步都"彻底失败" ⇒ 同一工具连败 3 次进 `failed_tools` ⇒ 下一步走降级分支。
    """
    import plan_execute as P

    def _explode(args):
        raise RuntimeError("工具内部炸了")

    monkeypatch.setitem(P._TOOL_HANDLERS, "calculator", _explode)
    # 每步都判"彻底失败" ⇒ 把同一工具推到 3 连败
    monkeypatch.setattr(P, "execute_step_with_quality_check",
                        lambda step, context, goal, name: "执行失败（已重试1次）：假装失败")
    # 重规划不许真调 LLM：给一份**同样只用 calculator**的计划，把循环推到降级分支
    monkeypatch.setattr(P, "plan_task",
                        lambda ctx: [_step("calculator") for _ in range(5)])

    out = P.execute_plan_with_replan([_step("calculator") for _ in range(5)], "目标", "u1")

    assert "工具内部炸了" in out, (
        "降级分支把真实失败原因吞了 ⇒ **兜底文案与真结果无法区分**。\n"
        f"实际输出：\n{out}"
    )


def test_plan_execute_has_no_bare_except():
    """结构判据：`plan_execute.py` 里**不许有裸 `except:`**（连 `KeyboardInterrupt` 都吞）。

    ⚠️ 与上一条**互补**：上一条管"原因有没有留下"，这一条管"别把整个解释器的中断信号也吃掉"。
       两者**跑真实业务都看不出**，所以都得是**结构性**判据。
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).with_name("plan_execute.py").read_text(encoding="utf-8")
    bare = [
        node.lineno
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.ExceptHandler) and node.type is None
    ]
    assert not bare, f"plan_execute.py 存在裸 except（行 {bare}）—— 请写成 except Exception"


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


def test_dynamic_input_receives_the_real_user_name(monkeypatch):
    """`generate_dynamic_input` 必须收到**真实发起人**。

    🔴 这条是**端到端实测**才发现的问题（2026-09-21）：
       `token_usage_logs` 里 `plan_execute.dynamic_input` 的 **4 条全记在 `unknown` 头上**，
       而 `plan` / `quality_check` 的记在 `admin` 头上。
       ⇒ 后果：**这部分额度算不到发起人头上 ⇒ 配额管不住他**（正是 ③-b 要解决的问题）。

    ⚠️ **根因值得记住**：那次改动用的是**盲替换** `s.replace(old, new, 1)` ——
       **命中了注释里的同一串**（注释在前 ⇒ 先被替换），**真正的调用点反而没改到**。
       📌 所以这条用例守的是「**调用点真的传了**」，
          ⛔ 不是「函数签名里有这个参数」（签名一直是对的）。

    ⚠️ 也**不能**只靠 `token_usage_logs` 来守 —— 那要真连库。这里用替身把判据做成**离线的**。
    """
    import plan_execute as P

    seen = {}

    def _fake_gen(step, context, user_goal, user_name="unknown"):
        seen["user_name"] = user_name
        return "假输入"

    monkeypatch.setattr(P, "generate_dynamic_input", _fake_gen)
    monkeypatch.setattr(P, "execute_step_with_retry", lambda *a, **k: "假结果")
    monkeypatch.setattr(P, "check_step_quality", lambda *a, **k: True)

    P.execute_step_with_quality_check(
        {"step": 1, "tool": "calculator", "action": "算一下"}, "", "目标", "someone_real"
    )

    assert seen.get("user_name") == "someone_real", (
        f"`generate_dynamic_input` 收到的是 {seen.get('user_name')!r} —— **不是真实发起人**。\n"
        "⇒ 这部分 token 会记在 `unknown` 头上 ⇒ 配额管不到真正用的人。\n"
        "⚠️ 检查是不是又漏传了（历史事故：盲替换命中了注释，真正的调用点没改到）。"
    )


# ===========================================================================
# ③ 遗留 #4 · 超时必须是【按实测校准】的 —— 既不能误杀，也不能吃光总预算
# ===========================================================================
# 实测基线（2026-09-21 · 28 次真实调用 · 见 `plan_execute.py` 里那张表）
_MEASURED_LLM_MAX_SEC = {"plan": 2.68, "dynamic_input": 1.77, "quality_check": 1.56}
_MIN_HEADROOM = 5  # 至少 5 倍余量


def test_llm_timeouts_are_calibrated_to_measurement():
    """超时**必须是按实测校准的** —— 两个方向都锁。

    · **下界**：每个超时 ≥ 实测 max 的 `_MIN_HEADROOM` 倍
      ⇒ 防止有人把它收得太紧（**LLM 延迟是重尾分布，观测到的 max ≠ P99**，收紧了会误杀正常请求）
    · **上界**：最坏单次（`timeout × (1+retries)`）**必须 < 总预算**
      ⇒ 否则【**一次卡住就能把整个计划的预算吃光**】，总预算形同虚设

    📌 这条是**遗留 #4** 的产物：原来那几个数（60/30/20）是**拍的**，对实测 max 有 13–22 倍余量；
       `plan` 的 60s 尤其糟 —— 60×(1+1)=120 **正好等于总预算** ⇒ **一次卡住就掐掉整个计划**。
    ⭐ 本用例把「**校准过**」这件事变成**可执行的**，而不是只写在注释里（注释会被改，判据不会）。
    """
    import plan_execute as P

    pairs = [
        ("planner_llm", P.PLANNER_LLM_TIMEOUT, _MEASURED_LLM_MAX_SEC["plan"]),
        ("executor_llm", P.EXECUTOR_LLM_TIMEOUT, _MEASURED_LLM_MAX_SEC["dynamic_input"]),
        ("quality_checker_llm", P.QUALITY_LLM_TIMEOUT, _MEASURED_LLM_MAX_SEC["quality_check"]),
    ]

    for name, timeout, measured in pairs:
        assert timeout >= measured * _MIN_HEADROOM, (
            f"{name} 超时 {timeout}s 对实测 max {measured}s 只剩 {timeout / measured:.1f} 倍余量 —— "
            f"至少要 {_MIN_HEADROOM} 倍。⚠️ LLM 延迟重尾，收太紧会误杀正常请求。"
        )

    worst_single = max(t for _, t, _ in pairs) * (1 + P.LLM_MAX_RETRIES)
    assert worst_single < P.PLAN_TOTAL_BUDGET_SECONDS, (
        f"最坏单次 = {worst_single}s ≥ 总预算 {P.PLAN_TOTAL_BUDGET_SECONDS}s —— "
        f"【一次卡住就能吃光整个计划的预算】，总预算形同虚设。"
    )


# ===========================================================================
# 🔴 把「FREE 用户对 plan_execute 的【真实】每日上限」钉住
# ===========================================================================
# 实测（2026-09-21）：一次 `plan_execute`（4 步目标）的真实 token 消耗。
# 测法：查 `token_usage_logs` 里 `user_name='admin'` 的**累计值** → 跑一次 → 再查 → 取差值。
#   ⇒ 27916 − 24570 = **3346 tokens**（该次 9 次 LLM 调用：1 规划 + 4 动态输入 + 4 质量检查）
# ⚠️ 会随目标步数浮动（3 步 + 一次真网络搜索那次更贵）⇒ 这里以 4 步的 3346 为基准。
_MEASURED_PLAN_EXECUTE_TOKENS = 3346


def test_free_users_real_daily_limit_on_plan_execute_is_known():
    """钉住 FREE 用户对 `plan_execute` 的**真实**每日上限（**token 口径**）。

    ## 历史：这条用例原本是「两套口径」的证据（`DEC-029`）—— ⚠️ 别整条删，那是个宝贵事实

    2026-09-21 实测时，本仓有**两套互不知情的配额**：

      | 口径 | 出处 | FREE 限额 | 对 `plan_execute` 的真实约束 |
      |---|---|---|---|
      | **请求次数** | `permission.ROLE_QUOTA`（中间件用） | **100/天** | ❌ **形同虚设** |
      | **Token** | `token_config.ROLE_DAILY_TOKEN` | **10_000/天** | ✅ **真正在拦的是它** |

    `plan_execute` 一次实测要花 **~3346 tokens** ⇒ **次数配额（100）根本用不完**
    ⇒ 两套口径**差约 35 倍**。这正是 `DEC-040` 裁「**统一到 token 一套**」的起因。

    🔴 2026-10-03（`DEC-046`）：**次数那套已整张删掉** ⇒ 本用例只留 token 口径。
       ⚠️ **「FREE 每天约 3 次」这个数【没有任何人选择过】** ——
          它是「日预算 ÷ 单次成本」算出来的**副作用**。本用例把它变成**已知且被测的**。

    📌 **谁改了 `ROLE_DAILY_TOKEN['free']`、或让 `plan_execute` 变贵/变便宜，这条会红** ——
       提醒去**重新实测单次消耗**并更新记录。
       ⭐ **这不是"防改动"，是"防不知情"。**
    """
    from token_tracker import ROLE_TOKEN_BUDGET

    by_tokens = ROLE_TOKEN_BUDGET["free"] / _MEASURED_PLAN_EXECUTE_TOKENS

    # 历史对照（**这条口径已不存在**，留着只为说明「3 次」有多意外）：
    #   旧「请求次数」口径 FREE = 100/天 ⇒ 按次数能跑 100 次，按 token 只能跑 ~3 次。
    _OLD_REQUEST_COUNT_FREE = 100

    assert 2 <= by_tokens <= 5, (
        f"FREE 用户每天实际能跑 **{by_tokens:.1f}** 次 plan_execute —— 与记录（**3.0**）不符。\n"
        f"  （token 预算 {ROLE_TOKEN_BUDGET['free']} ÷ 实测单次 {_MEASURED_PLAN_EXECUTE_TOKENS}）\n"
        f"⚠️ 若这是【有意】改的，请**重新实测单次消耗**、更新这条用例与 `DEC-029`；\n"
        f"⚠️ 若是【无意】的（比如改了预算表却没意识到会波及这条最贵的接口），那正好——本条就是为这个而设。"
    )
