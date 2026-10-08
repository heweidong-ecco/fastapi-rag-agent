# DEC-105 · 工具缓存遇到 Redis 不通 —— **fail-open**（直通执行、缓存失效、打 ERROR）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已实施（2026-10-08）** |
| **触发** | **批①「工具缓存收口」Task 2 暴露的新问题**（原施工单**没预见**）。<br>业务方 2026-10-08 在三选一里**当场裁定「fail-open」**。 |
| **类型** | 可用性取向 · 降级语义 · 错误可见性 |
| **落点** | `api/tool_cache.py`：`_warn_redis_down()` + `cached_tool` 的**四处** `except redis.RedisError` 分支 |
| **判据** | 见 §五（逐条可打印） |

---

## 一 · 要裁的是什么（**这是施工单没预见的一件事**）

批① Task 2 要把 `@cached_tool` 接进 `web_search` / `calculator` / `date_today` / `execute_python`。
动手前**实测**发现了一个施工单没写的连带后果：

| | 接缓存**前** | 接缓存**后** |
|---|---|---|
| `web_search` / `calculator` 要不要 Redis | ⛔ **不要** | 🔴 **要** |
| Redis 挂掉时 | **照常工作** | 🔴 **抛 `ConnectionError` ⇒ 该工具 500** |

🔵 **实测证据**（本机 2026-10-08 · 当时 Redis **确实没起**）：

```
$ ../venv/bin/python -m pytest test_search_tools.py -q
6 passed                                   ← 现状：不需要 Redis

$ python -c "<把 cached_tool 包上去，Redis 不通>"
接了缓存、Redis 不通 ⇒ 抛: ConnectionError Error 61 connecting to localhost:6379. Connection refused.
```

⇒ **这不是"缓存没生效"，是"把两个本来不依赖 Redis 的工具变成了依赖 Redis"**。
**这是一次运行时行为回归**，必须先裁。

## 二 · 三个备选

| 备选 | 评价 |
|---|---|
| **A · fail-open**（**选中**） | ✅ 与仓内既有取向**一致**；✅ 生产不回归；✅ 本地无 Redis 也能跑测试<br>⚠️ 代价：Redis 挂时**静默降级**（只有一条 ERROR 日志） |
| 乙 · 保持抛异常 | ✅ 简单，Redis 挂了**立刻可见**<br>⛔ **行为回归**：把两个不需要 Redis 的工具变成需要 ⇒ **Redis 一挂，搜索与计算一起不可用** |
| 丙 · 本轮只接 `calculator` | ✅ 改动面最小<br>⛔ 「**一处事实源**」这个批① 的目标**只完成一半** |

**⇒ 业务方裁 A。**

---

## 三 · 决策内容

### 3.1 捕获范围 🔴 **只捕 `redis.RedisError`，⛔ 不是 `except Exception`**

> **理由**：`except Exception` 会把**代码 bug** 伪装成"Redis 不通" ⇒ **真 bug 永远查不出来**。

📌 **这不是新发明** —— 本仓 `api/rate_limiter.py` 的 `S8` 兜底**就是这个形状**，
且**已有守卫**：`api/test_rate_limiter_resilience.py::test_只捕获redis错误_别的异常要照样冒泡`。
本 DEC **照抄那个形状**。

### 3.2 降级语义：**直通执行 + 缓存失效 + 一条 ERROR**

- 读缓存失败 ⇒ 直接调工具函数，**结果照常返回**
- 抢锁失败 ⇒ 同上（不抢锁、不写缓存）
- **写**缓存失败 ⇒ **只记日志**，本次结果**已经算出来了**，照常返回
- **删锁**失败 ⇒ **静默忽略** —— 锁 10 秒后自己过期，⛔ 不因此让调用失败

### 3.3 🔴 第一不变量：**`func` 绝不出现在任何 `except redis.RedisError` 的 `try` 里**

**为什么**：那样写的话，**工具自己抛 `RedisError`** 会被当成"缓存挂了" ⇒
`except` 分支里再 `return func(...)` ⇒ **工具被执行两遍**（双跑）。

⚠️ **这不是纸上风险**：`execute_python` 这类工具有副作用，双跑等于**执行两次**。
🔵 **实测**（本仓 2026-10-08）：一个"朴素版"（`func` 放在 `except` 的 `try` 内）在工具抛
`RedisError` 时**执行次数 = 2**。
📌 守卫：`api/test_tool_cache.py::test_tool_raising_redis_error_is_not_retried`。

---

## 四 · 反悔成本

| 项 | 成本 |
|---|---|
| 改回"抛异常"（乙） | **低** —— 删掉四处 `except` 分支即可；⚠️ 但要**同时**把"工具依赖 Redis"写进运维/健康检查 |
| 改回"只接 calculator"（丙） | **中** —— 要把 `web_search` 的包裹撤掉，并回退它的测试 |
| 收紧捕获范围 | **零** —— 本来就是 `redis.RedisError` |

---

## 五 · 判据（**逐条可打印**）

```bash
# ① fail-open 成立：Redis 不通时工具照常返回结果（⛔ 不抛）
cd api && ../venv/bin/python -m pytest test_tool_cache.py -q -k "falls_open"

# ② 只捕 RedisError：非 Redis 异常照样冒泡
cd api && ../venv/bin/python -m pytest test_tool_cache.py -q -k "still_bubbles"

# ③ 不许双跑
cd api && ../venv/bin/python -m pytest test_tool_cache.py -q -k "not_retried"

# ④ 端到端：本机【没起 Redis】时，搜索工具的既有用例仍然全绿
cd api && ../venv/bin/python -m pytest test_search_tools.py test_impl_modules.py \
                                    test_safe_math_wiring.py -q

# ⑤ ④ 的前提：先证明本机 Redis **确实没起**（⛔ 别用 `redis-cli ping` —— 本机没装）
cd api && ../venv/bin/python -c "import redis; redis.Redis().ping()"
# 实测输出：redis.exceptions.ConnectionError: Error 61 connecting to localhost:6379.
#           Connection refused.
```

⚠️ **④ 是关键的一条**：它是"fail-open 真的接上了"的**唯一端到端凭证** ——
**⑤ 先证明 Redis 确实没起**，而 ④ 那 41 条**照样全绿**。

📌 **2026-10-08 更正**：本 DEC 初稿的 ⑤ 写的是 `redis-cli ping` —— **本机根本没装
`redis-cli`**（`command -v redis-cli` 空 · `/opt/homebrew/bin` 与 `/usr/local/bin` 下都没有）。
⇒ 那是一条**跑不起来的判据**，已换成上面那条。**教训**：判据不仅要"写成命令"，
**还要确认那条命令在本机真能跑** —— 否则它与没写一样。

## 六 · 边界

1. ⛔ **别把这理解成"Redis 可以不装"** —— 缓存**仍然需要** Redis 才生效；
   fail-open 只保证**不可用时不影响正确性**，⚠️ **不保证性能**。
2. ⚠️ **静默降级是本决定已知的代价** —— 机器痕迹上「缓存从不命中」与
   「根本没在缓存」**长得一样**（本仓原话：**「『从不命中』与『没人违规』在机器痕迹上完全一样」**）。
   ⇒ 只能靠那条 ERROR 日志与健康检查发现。**⛔ 别因为"反正会降级"就不管 Redis 的健康。**
3. ⛔ **不许把捕获范围放宽成 `except Exception`** —— 见 §3.1，有守卫用例守着。
4. ⛔ **不许把 `func` 挪进 `except redis.RedisError` 的 `try`** —— 见 §3.3，有守卫用例守着。

---

## 关联

- **本决定服务的那件事** ⇒ `DEC-104` 的 **§2.2 ①「清单统一」**（批① 工具缓存收口）
- **同形先例（照抄它的形状）** ⇒ `api/rate_limiter.py` 的 `S8` 兜底 ·
  守卫 `api/test_rate_limiter_resilience.py::test_只捕获redis错误_别的异常要照样冒泡`
- **本仓判据纪律** ⇒ `CLAUDE.md`「判据」表（**判据要写成命令** + **反证检验**）
- ⚠️ **本 DEC 的监督脚本**：`scripts/check_lint_baseline.sh`（第 ⑥ 道门）与
  `.claude/hooks/pre-commit-gates.py`（提交前六道门）
