"""额度常量的【唯一来源】的回归测试（对应 B7）。

⛔ 本文件不碰 DB / Redis —— 只读常量。
"""
import token_config


def test_single_call_caps_are_the_agreed_values():
    """业务方 2026-09-30 裁的起始值。⚠️ 终值等前端做完、浏览器实测后再调。"""
    assert token_config.MAX_TOKENS_ANSWER == 2000
    assert token_config.MAX_TOKENS_AGENT == 1024


def test_admin_is_no_longer_infinite():
    """🔴 业务方 2026-09-30 裁：「admin 也要同样上限」⇒ 不许是 inf。"""
    assert token_config.ROLE_DAILY_TOKEN["admin"] != float("inf")
    assert token_config.ROLE_DAILY_TOKEN["admin"] == token_config.ROLE_DAILY_TOKEN["premium"]


def test_single_call_cap_does_not_depend_on_role():
    """单次上限【不分角色】—— 否则对 admin 等于不存在。"""
    assert not hasattr(token_config, "ROLE_MAX_TOKENS")


# ==================== 兜底额度必须是【最低档】，⛔ 不是最高档（丁 · 2026-10-04） ====================

def test_every_role_has_a_registered_budget():
    """推导型守卫：`permission.UserRole` 里**每一个**角色都必须登记在 `ROLE_DAILY_TOKEN`。

    **为什么**：`get_user_token_budget()` 是
    `ROLE_TOKEN_BUDGET.get(role, DEFAULT_DAILY_TOKEN_BUDGET)` ——
    **角色没登记 = 静默落进兜底**（⛔ 不报错、不告警）。
    ⇒ 本条的判据是**推导的**（从 enum 推出名单），⛔ 不是"记住 free/premium/admin 三个名字"
      —— 名单型守卫只钉住"当时知道的那几个"，新增角色时**它不会响**。

    ⚠️ **坦白一句**：本条**从建立起就是绿的**（三个角色当天都登记了）。
       它钉的是**不变量**，⛔ 不是"修了某个 bug" —— 别把它读成"抓到过什么"。
    """
    from permission import UserRole
    for role in UserRole:
        assert role.value in token_config.ROLE_DAILY_TOKEN, (
            f"🔴 角色 {role.value!r} 没有在 token_config.ROLE_DAILY_TOKEN 里登记 "
            f"⇒ 它会静默落进兜底值 {token_config.DEFAULT_DAILY_TOKEN_BUDGET}"
        )


def test_unregistered_role_falls_back_to_the_LOWEST_tier_not_the_highest():
    """🔴 兜底额度必须 ≤ **现存最低档** —— 本仓取向是 fail-closed，这条是它的下限。

    **改前的事实**（2026-10-04 实测）：兜底值是 `100_000`，**等于 `premium`（最高档）**
    ⇒ 角色名拼错 / 新角色忘了登记，用户**静默拿到最高额度**，且**没有任何东西会响**。

    ⚠️ 判据是**推导的**（⛔ 不是把 `10_000` 写死）：`兜底 ≤ min(各档)`。
    ⇒ 将来真加了比 `free` 还便宜的一档，兜底**必须跟着降**，否则本条转红。
    """
    lowest = min(token_config.ROLE_DAILY_TOKEN.values())
    assert token_config.DEFAULT_DAILY_TOKEN_BUDGET <= lowest, (
        f"🔴 未登记角色的兜底日预算 ({token_config.DEFAULT_DAILY_TOKEN_BUDGET}) "
        f"高于现存最低档 ({lowest}) ⇒ 角色名打错就静默拿到**更多**额度（fail-open）。"
    )


def test_an_unregistered_role_actually_gets_the_lowest_budget(monkeypatch):
    """走**真函数**（⛔ 不只看常量）：一个**没登记**的角色 ⇒ 落兜底，且兜底 = 最低档。

    ⚠️ 为什么必须走 `get_user_token_budget()`：**常量改成 10_000、函数仍读别处**
       是另一类假完成（同 `test_rate_limiter_actually_reads_token_config` 记的那个形状）。

    ⚠️ 为什么**不能**拿 `get_user_token_budget("__no_such_user__")` 来测：
       `get_user_role()` 对未知用户名返回 `FREE` —— 而 `free` **是登记过的**
       ⇒ 那条会走**正常路径**，⛔ **根本碰不到兜底**，改前也是绿的（= 一条测不出东西的用例）。
       ⇒ 必须**强行**让取角色那步返回一个不存在的角色。
    """
    import permission
    import token_tracker

    monkeypatch.setattr(permission, "get_user_role", lambda _user: "unregistered_role")

    budget = token_tracker.get_user_token_budget("anyone")
    lowest = min(token_config.ROLE_DAILY_TOKEN.values())
    assert budget == lowest, (
        f"未登记角色拿到了 {budget}，最低档是 {lowest} ⇒ 兜底没有 fail-closed"
    )


# ==================== S5 · 在用的模型必须**明确**配价 ====================

def test_models_actually_in_use_have_explicit_pricing():
    """🔴 在用的模型**不许**落到兜底价 —— 兜底价看不出来是兜底（`🅗 S5`）。

    `.env` 里 `LLM_MODEL_FAST` / `LLM_MODEL_CHAT` 走的是 DeepSeek
    （`docs/契约/环境变量.md:70`），而原先 `PRICING` **只有 qwen 系列** ⇒
    金额按兜底价算，**没有任何地方看得出它是兜底**。
    """
    # ⚠️ 从 config 取，不写死模型名 —— 换 `.env` 时这条测试跟着走
    from config import LLM_MODEL_FAST, LLM_MODEL_CHAT
    for name in (LLM_MODEL_FAST, LLM_MODEL_CHAT):
        assert name in token_config.MODEL_PRICING, (
            f"在用的模型 {name!r} 不在 MODEL_PRICING 里 ⇒ 金额会落到兜底价，"
            f"且看不出来。当前已登记：{sorted(token_config.MODEL_PRICING)}"
        )


def test_embedding_model_still_priced():
    """Embedding 也按 model 记账（`embedding_client.py:32`）—— 别在搬家时漏掉。"""
    assert "text-embedding-v2" in token_config.MODEL_PRICING


def test_all_registered_prices_are_positive():
    """登记的单价不许是 0 或负数 —— 那会**静默把花费记成 0**。

    ⚠️ **本条替代了原先的 `test_default_pricing_is_not_lower_than_models_in_use`**（2026-10-01 删）。
       那条断言「兜底价 >= 在用模型价」，**在 CI 上直接红**：
       CI 没有 `.env` ⇒ `config.LLM_MODEL_CHAT` 落到**代码里的默认值**
       （**当时**是 `config.py:55` 的 `qwen-plus`；⚠️ **2026-10-02 起已改成 `deepseek-v4-flash`**，
       见 `DEC-045` —— 这条记的是**那天**的事实）
       ⇒ 0.008/0.016 **本来就高于**兜底 0.003/0.006 ⇒ `assert 0.003 >= 0.008` 失败。
    🔴 **根因不是"CI 配置特殊"，是那条不变量本身不成立** ——
       兜底价是给**未登记**模型的猜测值，**与"在用模型贵不贵"没有推导关系**；
       而在用模型**只要登记了就永远不走兜底** ⇒ 那条断言**给不出任何保护**，
       却会随部署选哪个模型而时红时绿。**这是"我发明了一条规矩"的第二次**（第一次见 commit `8a5672b`）。
    📌 **真正防"静默低报"的是上面那条**（在用模型必须登记），⛔ 不是这个兜底价。
    """
    for name, p in token_config.MODEL_PRICING.items():
        assert p["prompt"] > 0, f"{name} 的 prompt 价 <= 0 ⇒ 花费会被静默记成 0"
        assert p["completion"] >= 0, f"{name} 的 completion 价为负"
    d = token_config.DEFAULT_MODEL_PRICING
    assert d["prompt"] > 0 and d["completion"] > 0, "兜底价必须为正，否则未登记模型的花费记成 0"


# ==================== S6 · 限流参数也收进来 ====================

def test_record_usage_never_hardcodes_a_model_name():
    """🔴 `record_usage(model="…")` 不许写死字符串（`🅗 S4`）。

    为什么：`.env` 换模型（qwen → deepseek）时，写死的地方**不会跟着改**，
    而**金额按旧模型的单价算**，且从数字上看不出来。本仓实测栽过 3 处
    （`agent_graph_advanced.py` ×2 · `agent_checkpointer.py` ×1）。

    ⚠️ 用 AST 而不是 grep —— 注释与 docstring 里也有同样的串（本仓栽过，
       见 `docs/规范/开发规范.md` §3.1「批量替换后按【位置】核」）。
    """
    import ast
    import pathlib
    offenders = []
    for p in sorted(pathlib.Path(__file__).parent.glob("*.py")):
        if p.name.startswith("test_"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) != "record_usage":
                continue
            for kw in node.keywords:
                if kw.arg == "model" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    offenders.append(f"{p.name}:{node.lineno} → model={kw.value.value!r}")
    assert not offenders, (
        "这些 record_usage 把模型名写死了 ⇒ 换模型后金额会算错：\n  " + "\n  ".join(offenders)
    )


# ==================== B7 · 搬家是【真搬】，不是复制一份 ====================

def test_tracker_aliases_point_at_token_config():
    """🔴 别名必须**是同一个对象**，⛔ 不是"值相同的新字典"。

    ⚠️ 光比值分不出"搬了"还是"抄了一份" —— 抄的那份**下次改价时不会跟着动**，
       而这正是这个 Task 要解决的问题本身。
    """
    import token_tracker
    assert token_tracker.PRICING is token_config.MODEL_PRICING
    assert token_tracker._DEFAULT_PRICING is token_config.DEFAULT_MODEL_PRICING
    assert token_tracker.ROLE_TOKEN_BUDGET is token_config.ROLE_DAILY_TOKEN
    assert token_tracker.MAX_SINGLE_CALL_COST is token_config.MAX_SINGLE_CALL_COST
    assert token_tracker.MAX_THREAD_COST is token_config.MAX_THREAD_COST


def test_rate_limiter_params_are_centralized():
    """限流参数与额度参数**同型**（都是写死）⇒ 一起收口（`🅗 S6`）。"""
    for attr in ("GLOBAL_LIMIT_RATE", "GLOBAL_LIMIT_CAPACITY",
                 "USER_LIMIT_RATE", "USER_LIMIT_CAPACITY"):
        assert isinstance(getattr(token_config, attr), (int, float)), attr


def test_rate_limiter_actually_reads_token_config():
    """🔴 常量搬了家、**限流器没读** = 没搬（同「B7 接线」那类假完成）。

    ⚠️ **光比值没用** —— 若两边都写 100.0，"读了"与"恰好同值"分不出来。
    ⇒ 改成**用环境变量把值改掉**，另起一个进程导入 ⇒ 只有真读了 `token_config` 才可能对上。
    """
    import os
    import subprocess
    import sys

    code = (
        "import token_config, rate_limiter;"
        "assert token_config.GLOBAL_LIMIT_RATE == 7.5, token_config.GLOBAL_LIMIT_RATE;"
        "assert token_config.USER_LIMIT_CAPACITY == 11, token_config.USER_LIMIT_CAPACITY;"
        "assert rate_limiter.global_limiter.rate == 7.5, rate_limiter.global_limiter.rate;"
        "assert rate_limiter.user_limiter.capacity == 11, rate_limiter.user_limiter.capacity;"
    )
    env = {**os.environ,
           "GLOBAL_LIMIT_RATE": "7.5", "USER_LIMIT_CAPACITY": "11",
           "GRADIO_ANALYTICS_ENABLED": "False"}
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        "改环境变量后限流器没跟着变 ⇒ 它没读 token_config：\n" + r.stderr[-800:]
    )
