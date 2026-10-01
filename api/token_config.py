"""额度配置的【唯一落点】（B7 · 2026-10-01 落盘）。

为什么建这个文件：在此之前，额度类常量**散在 4 个文件 6 处**，且**单位混着**：
  · `permission.ROLE_QUOTA`（**次数**）
  · `token_tracker.ROLE_TOKEN_BUDGET`（token）· `MAX_THREAD_COST`（**元**）· `MAX_SINGLE_CALL_COST`（**元**）
  · `token_tracker.PRICING`（元/1000token）
  · `plan_execute.PLAN_TOTAL_BUDGET_SECONDS`（**秒**）
⇒ 这正是 `DEC-029`「两套口径差 35 倍」与 `决策一`「三套怎么合」的**物理原因**。
📄 口径的裁定见 `docs/decisions/DEC-040-额度统一到token一套.md`。

⚠️ **本模块只读 env，不做热加载** —— 故意的。
   `ChatOpenAI(model=…, max_tokens=…)` 是 **import 时求值**（17 个构造点全是），
   改了值本来就要重启。**只求"集中"，不求"热加载"。**
"""
import os


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


# ==================== 单次上限（token）· ⛔ 不分角色 ====================
# 行业区间 500–2000（见 后端补齐清单 B7 附的检索来源）。
# ⚠️ 取上沿而不是"中和"：压低到 1800 以下**会开始截断答案**。
MAX_TOKENS_ANSWER = _int("TOKEN_MAX_ANSWER", 2000)   # RAG 答案生成 / WS agent
MAX_TOKENS_AGENT = _int("TOKEN_MAX_AGENT", 1024)     # Agent 对话 / planner / 质检
# 查询改写**已有自己的值**（query_rewriter.py:65/143），此处只登记、不改行为
MAX_TOKENS_REWRITE_VARIANTS = _int("TOKEN_MAX_REWRITE_VARIANTS", 200)
MAX_TOKENS_REWRITE_INTENT = _int("TOKEN_MAX_REWRITE_INTENT", 800)

# ==================== 分层上限（token）· 由后续计划接线 ====================
SESSION_TOKEN_LIMIT = _int("SESSION_TOKEN_LIMIT", 50000)          # B8（①b）
GLOBAL_DAILY_TOKEN_LIMIT = _int("GLOBAL_DAILY_TOKEN_LIMIT", 1_000_000)  # B10（①b）

# ==================== 角色日预算（token） ====================
# ⚠️ 档位体系【本轮不重塑】—— 业务方 2026-09-30：「还没有想好『分几档』，留第二轮」。
#    本轮只把 admin 的 inf 换掉。
# ⚠️ 键是**字符串**（角色的 value），与 `permission.UserRole`（str Enum）可比 ——
#    见 `token_tracker.get_user_token_budget()` 的 `.get(role, …)` 用法。
ROLE_DAILY_TOKEN = {
    "free": _int("DAILY_TOKEN_FREE", 10_000),
    "premium": _int("DAILY_TOKEN_PREMIUM", 100_000),
    # ✅ 2026-09-30 裁（实施 2026-10-01）：admin = premium，⛔ 不再是 float("inf")
    "admin": _int("DAILY_TOKEN_ADMIN", 100_000),
}

# 未登记角色的兜底日预算（迁自 `token_tracker.py:283`）
DEFAULT_DAILY_TOKEN_BUDGET = _int("DEFAULT_DAILY_TOKEN_BUDGET", 100_000)

# ==================== 模型单价（元 / 1000 tokens） ====================
# 迁自 `token_tracker.PRICING`（:50）。⚠️ 加新模型时**只改这里**。
MODEL_PRICING = {
    "qwen-turbo": {"prompt": 0.003, "completion": 0.006},
    "qwen-plus": {"prompt": 0.008, "completion": 0.016},
    "text-embedding-v2": {"prompt": 0.0005, "completion": 0},
    # ⚠️ 2026-10-01 补（🅗 S5）：`.env` 里 LLM 实际走 DeepSeek
    #    （`docs/契约/环境变量.md:70`），而原先这张表**只有 qwen 系列** ⇒
    #    金额落到兜底价，**且没有任何地方看得出它是兜底**。
    # 📌 单价来源：DeepSeek 官方人民币口径「输入 1 元 / 输出 2 元 每百万 token」
    #    ⇒ 本表单位是元/1000 ⇒ 0.001 / 0.002。
    #    ⚠️ 缓存命中的输入价更低（官方约 0.2 元/百万），本表**不区分缓存** ——
    #    我们是按 `usage_metadata` 的 token 数算，拿不到"命中/未命中"的拆分 ⇒
    #    按**未命中**价记 ⇒ **偏高估**（偏保守，与兜底价的取向一致）。
    "deepseek-v4-flash": {"prompt": 0.001, "completion": 0.002},
}
# 未登记模型的**兜底单价**。
# 🔴 **2026-10-01 更正一句旧话**：原来这里写「取偏保守的一组（**不低报**花费）」——
#    **这句话是错的，别信**。它是 qwen-turbo 那个年代的说法：0.003/0.006 恰好等于 qwen-turbo 的价，
#    所以对"比 qwen-turbo 便宜"的模型才是保守的；而**对 `qwen-plus`（0.008/0.016）它明确是低报**。
#    ⇒ **兜底价不是任何意义上的上界。**
# ⚠️ **真正防"静默低报"的是这件事：【在用的模型必须登记】**（见 `api/test_token_config.py`
#    的 `test_models_actually_in_use_have_explicit_pricing`）——
#    只要登记了，就**永远不走兜底**；兜底只对**彻底未知**的模型生效，而那本来就没法估。
DEFAULT_MODEL_PRICING = {"prompt": 0.003, "completion": 0.006}

# ==================== 花费上限（元）· 多级预算的第一、二级 ====================
MAX_SINGLE_CALL_COST = _float("MAX_SINGLE_CALL_COST", 0.5)
MAX_THREAD_COST = _float("MAX_THREAD_COST", 5.0)

# ==================== 限流参数（🅗 S6） ====================
# 与上面的额度参数**同型**（原先都写死在 `rate_limiter.py:129/132`）⇒ 一起收口。
GLOBAL_LIMIT_RATE = _float("GLOBAL_LIMIT_RATE", 100.0)      # 全局：每秒补充令牌数
GLOBAL_LIMIT_CAPACITY = _int("GLOBAL_LIMIT_CAPACITY", 150)  # 全局：桶容量（突发上限）
USER_LIMIT_RATE = _float("USER_LIMIT_RATE", 3.0)            # 单用户：每秒补充
USER_LIMIT_CAPACITY = _int("USER_LIMIT_CAPACITY", 20)       # 单用户：桶容量
