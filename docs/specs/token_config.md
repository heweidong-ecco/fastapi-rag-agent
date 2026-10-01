# `api/token_config.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟢 **新建（2026-10-01 · B7）** —— 额度类常量的**唯一落点**，**只集中，不改行为**<br>⚠️ **常量已就位，但【尚未接线】** —— 17 个 `ChatOpenAI` 构造点还没读 `MAX_TOKENS_*`（排 `①b` Task 1） |
| **对外提供** | `MAX_TOKENS_ANSWER` · `MAX_TOKENS_AGENT` · `MAX_TOKENS_REWRITE_*` · `SESSION_TOKEN_LIMIT` · `GLOBAL_DAILY_TOKEN_LIMIT` · `ROLE_DAILY_TOKEN` · `DEFAULT_DAILY_TOKEN_BUDGET` · `MODEL_PRICING` · `DEFAULT_MODEL_PRICING` · `MAX_SINGLE_CALL_COST` · `MAX_THREAD_COST` · `GLOBAL_LIMIT_*` · `USER_LIMIT_*` |
| **谁在用** | `token_tracker.py`（别名 `PRICING` / `ROLE_TOKEN_BUDGET` / …）· `rate_limiter.py`（`:129` 起两个既有 `TokenBucketLimiter` 的实例化）<br>⬜ **尚未接**：17 个 `ChatOpenAI(max_tokens=…)` 构造点（`①b · Task 1`）· B8/B10 的判定函数（`①b`） |
| **规模** | 89 行（`wc -l api/token_config.py`） |

## ✅ 做了什么

- **把散在 4 个文件 6 处的额度常量收到一处** —— 这是 `DEC-029`「两套口径差 35 倍」与
  `决策一`「三套怎么合」的**物理原因**（单位混着：次数 / token / 元 / 秒）。
- **按 `DEC-040`（决策一 = 统一到 token）**：`ROLE_DAILY_TOKEN["admin"]` **不再是 `float("inf")`**，
  = `premium` = **100000 token/天**（业务方 2026-09-30 裁）。
- **补 `deepseek-v4-flash` 单价**（`🅗 S5`）—— 原先表里**只有 qwen 系列**，
  而 `.env` 实际走 DeepSeek ⇒ 金额落兜底价，**且看不出来是兜底**。
- **收限流参数**（`🅗 S6`）—— `rate_limiter.py` 原先把 `100/150` `3/20` 写死在 `:129/:132`。

## 🟡 做到哪 / 缺什么

- ⬜ **没有任何构造点真的读 `MAX_TOKENS_*`** —— 常量建好了，**接线在 `①b · Task 1`**。
  ⚠️ **常量对了、没接上 = 单次上限不存在**（`test_max_tokens_wiring.py` 就是为它准备的）。
- ⬜ **`SESSION_TOKEN_LIMIT` / `GLOBAL_DAILY_TOKEN_LIMIT` 只有值，没有判定函数**（B8/B10，`①b`）
- ⬜ **`MAX_TOKENS_REWRITE_*` 只登记、不改行为** —— `query_rewriter.py:65/143` 仍是自己的字面量
- ⬜ **零 env 覆盖测试** —— 默认值测了，`os.getenv` 那条路只对限流参数用子进程验过一次
- ⚠️ **`permission.ROLE_QUOTA`（次数）本轮【没动】** —— 按 `DEC-040` 它要在
  **`①b · Task 6`【最后】**降级（先撤次数会开出"谁都不拦"的窗口，见该 DEC 的「顺序陷阱」）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「常量集中了 ⇒ 就动态了 / 能热加载了」** | ⛔ **不是** —— **只集中，不做运行时路由**。`ChatOpenAI(max_tokens=…)` 是 **import 时求值**（17 个构造点全是）⇒ **改了值本来就要重启容器**。这两件事**不是一回事** |
| 🔴 **「在 `token_config` 里改个值，服务行为立刻变」** | ⛔ **不是** —— 见上。且**多数常量还没有调用方**（⬜ 接线在 `①b`） |
| ⚠️ **「`MODEL_PRICING` 里的 `deepseek` 价就是账单价」** | 🟡 **是近似** —— 本表**不区分缓存命中**（拿不到命中/未命中的拆分）⇒ 按**未命中**价记 ⇒ **偏高估**（偏保守）。来源见文件内注释 |
| 🔴 **「兜底价是个上界 / 它不会低报花费」** | ⛔ **不是，而且旧注释就是这么写错的**。原注释写「取偏保守的一组（**不低报**花费）」——**那是 qwen-turbo 年代的说法**（0.003/0.006 恰好等于 qwen-turbo 的价）。实测：**`qwen-plus`（0.008/0.016）本来就高于兜底**。<br>⇒ **兜底价不是任何意义上的上界**；**⛔ 别拿它当规矩**。<br>📌 **真正防"静默低报"的是「在用模型必须登记」**（登记了就走自己的价，**永远走不到兜底**）。<br>🔴 **本行是两个坑的合体**：① 我先把那句旧注释当成了规矩；② 又把它写成测试 ⇒ **CI 直接红**（CI 无 `.env` ⇒ `config.py:55` 默认 `qwen-plus`）⇒ 已删该测试，见 `api/test_token_config.py` 顶部 docstring |
| ⚠️ **「`ROLE_DAILY_TOKEN` 的键是枚举」** | ⛔ **是字符串**（`"free"`/`"premium"`/`"admin"`）。能对上是因为 `permission.UserRole` 继承 `str` ⇒ ⚠️ **改 `UserRole` 的值就会静默错配**（`.get(role, 默认值)` 不报错，直接吃默认值） |
| ⚠️ **「建了 `token_config` ⇒ 另三套口径没了」** | ⛔ **还在** —— `permission.ROLE_QUOTA`（次数）与 `quota_limiter.py`（每日次数）**本轮一行没动** |

## 关联

`docs/decisions/DEC-040-额度统一到token一套.md`（**口径裁定**）· `DEC-029`（**实测差 35 倍**，已收口）·
`docs/specs/token_tracker.md`（`①a`/`①b` 的实施计划全文）· `docs/specs/rate_limiter.md` · `docs/specs/permission.md`（⏳ 待建）
