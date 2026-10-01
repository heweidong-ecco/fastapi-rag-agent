# `api/rate_limiter.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 基于 Redis 的令牌桶，**全局 + 用户两层**<br>🔴 **但它有 3 个"看代码看不出来"的性质**（见下 ⚠️ 节）—— 其中 2 条是本 spec 新查出来的 |
| **对外提供** | `TokenBucketLimiter`（`is_allowed` / `get_remaining` / `get_limit_info`）· 两个模块级实例 `global_limiter` · `user_limiter` |
| **谁在用** | `main.py:21` 的 `RateLimitMiddleware`（**唯一的生产消费者**）· `api_v1.py:31` 的 `/debug/*` 查询端点 |
| **规模** | 140 行 |

## ✅ 做了什么

- **令牌桶**（`:32` `is_allowed`）：整段判定写在 **Lua 脚本**里（`:41-68`）⇒ **原子**，不会被并发拆开
- **回填是【惰性】的**：在 Lua 里 `elapsed = now - last_time` ⇒ `tokens += elapsed*rate`（`:56-58`）——
  ⚠️ 这条曾经被**误报成"桶不回填"**（N16），核了消费入口才撤回（见 `:103-107` 的注释）
- **只读展示**：`get_remaining`(`:81`) · `get_limit_info`(`:90`，返回 `remaining`/`reset`/`limit` 三个值供响应头用)
- **两层实例**（`:129/132`）：`global_limiter` = 100/s · 容量 150 ｜ `user_limiter` = 3/s · 容量 20

## 🟡 做到哪 / 缺什么

- 🔴 **桶【永不过期】** —— 全文 **0 个 `EXPIRE` / `TTL`** ⇒ Redis 里 `rate_limit:*` 键**永久累积**（见 ⚠️②）
- 🔴 **Redis 不通 ⇒ 非公开路径【全站 500】** —— 没有 `except RedisError`（见 ⚠️③）
- 🔴 **零单测** —— `docs/说明/测试.md:185` 自述「**前者间接**、后者零覆盖」；
  它只被 `test_rag_search.py` 的 L1/L2 **间接**依赖（那两条**必须真连 Redis**）
- ✅ ~~⚠️ **限流参数写死在代码里**（`:129/132`），⛔ 不是 env~~ ⇒ **2026-10-01 已收口**（`🅗 S6`）：
  两个 `TokenBucketLimiter` 的 `rate`/`capacity` 改从 **`api/token_config.py`** 取
  （`GLOBAL_LIMIT_RATE` / `GLOBAL_LIMIT_CAPACITY` / `USER_LIMIT_RATE` / `USER_LIMIT_CAPACITY`）。
  ⚠️ **默认值逐字相同 ⇒ 行为不变**；📌 它**不是热加载**（`token_config` 只读 env，改值仍要重启）
- ⚠️ **死导入**：`Request` / `HTTPException` / `os`（`:3-4`）**全都没用到**

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **① 形参 `user_name` 是"用户名"** | ⛔ **不是** —— 它是**桶名**。实际传进来的有 `"global"`（`:153`）· `"anonymous"` · `"user:<真实用户名>"`。<br>⚠️ **2026-09-30（B9-b）之前**，`"user:..."` 那段是 **`X-API-Key` 的前 8 个字符**，**不验签** ⇒ **编一个串就换一个桶**。<br>📌 **所以本文件的 `user_name` 一词是误导性的** —— 读它时请替换成"桶名"。<br>（B9-b 已修：验不过 ⇒ 落 `anonymous` 桶。见 `docs/specs/main.md`） |
| 🔴 **② 「桶会自动过期」** | ⛔ **不会**。全文**只有 `HSET`、没有 `EXPIRE`** ⇒ 键**永久留在 Redis**。<br>🔴 **与 ① 叠加后是个真问题**：**修 B9-b 之前**，任意伪造的 key 都能造一个**新桶** ⇒ **Redis 键无限增长** ⇒ 那不只是"刷限流"，是**内存耗尽型的 DoS**。<br>✅ **B9-b 把它堵住了**（伪造 key 现在落匿名桶）——⚠️ **但存量键仍在、且新键依然不过期**。⬜ **是否该加 `EXPIRE`？未裁。** |
| 🔴 **③ 「Redis 挂了只是限流失效，请求照过」** | ⛔ **反了 —— 是非公开路径【全站 500】**。<br>**这不是推断**：`api/test_rag_search.py:15` 早就写着「**`rate_limiter.py` 没有 `except RedisError` ⇒ Redis 不通时全站 500（实测）**」。<br>⚠️ **而且拿不到结构化错误** —— `main.py:186` 的注释写明「**中间件中抛出的异常不会被 `@app.exception_handler(AppException)` 捕获**」（会落到 `ServerErrorMiddleware` 的通用处理器）。<br>⛔ **与 `token_tracker` 的取舍【故意相反】**：那边查库失败是 **fail-open**（放行）；这边是 **fail-closed 且炸成全站 500**。**两者都不是"显然对"**，但**至少该是有意识的**。 |
| ⚠️ **④ `get_limit_info()` 给的是"此刻的剩余"** | ⛔ **不是** —— 它算的是**消费【前】**的值：`main.py:175` 调它、`:179` 才调 `is_allowed`；而放行分支（`:203-208`）**用的就是那个 `info`**，**没有重算**。<br>⇒ **响应头 = 上一个状态的剩余**，⛔ 不是本次请求之后的。 |

> ### ✅ ④ 的实测（2026-09-30 · **服务真跑着时验的**）
>
> ```bash
> # 快发 8 次（快过 3/秒 的回填），每次记下响应头
> for i in $(seq 1 8); do
>   curl -s -o /dev/null -D - "http://127.0.0.1:8000/api/v1/agent/available_tools" \
>     | grep -i x-ratelimit-remaining
>   sleep 0.1
> done
> # 然后直接问 Redis 桶里真实的 tokens
> docker exec redis-rag redis-cli HGETALL rate_limit:anonymous
> ```
>
> | 次 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | **Redis 里实际** |
> |---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
> | `X-RateLimit-Remaining` | 19 | **19** | 18 | 17 | 16 | 15 | 14 | **13** | **12** |
>
> **✅ 证实的事实**：
> 1. **限流确实在工作** —— 计数在降（13 → 说明确实在扣）
> 2. 🔴 **响应头比 Redis 里的真实值【恒定多 1】**（末次 `13` vs 实际 `12`）
>    ⇒ **正是"消费前 vs 消费后"那一格之差**
>
> **⚠️ 尚未解释的**：**第 1、2 次都是 19**（没降）。
> 我**试过几种解释都对不上**（回填速率 / 惰性回填 / 中间件顺序），**所以不写结论**。
> ⬜ **谁要接着查**：先量一次**单轮迭代的真实耗时**（`sleep 0.1` + curl 往返可能已 > 0.33 秒，
> 那会让"回填 1、消耗 1"净持平）——**这是最可能的解释，但没验过**。
>
> 📌 **本条是一次"差点写进 spec 的未验证结论"** —— 初稿我只写了"多报 1"，
> 那是**从代码推的**；实测把"多 1"坐实了，**却同时暴露出一个我解释不了的现象**。
> ⇒ **先量、再写**（同 `docs/复盘/2026-09-30-本地绿当成了不依赖.md`）。
| ⚠️ **⑤ 「两个 limiter 是分开的两层，互不影响」** | ✅ **对，但有个隐含前提**：`global_limiter.is_allowed("global")` 用的是**同一个 `TokenBucketLimiter` 类**、只是桶名不同 ⇒ **全局那层也是"每人一份"的算法**，只是所有人共用一个叫 `global` 的桶。<br>⇒ 它**不是**"全站总速率的另一种实现"，**就是同一个桶**。 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/main.md` | **唯一的生产消费者**（`RateLimitMiddleware`）· `resolve_rate_limit_identity()` 的「分桶 ≠ 鉴权」 |
| `docs/specs/quota_limiter.md` | **每日次数**那一层（⚠️ 与限流**不是一回事**：**限流管频率，配额管总量**） |
| `后端补齐清单` **B9** | 匿名按 IP 分桶 · 配额对匿名生效（⏸ **已挂起，挂了钩子**） |
| `后端补齐清单` **B9-b** | ✅ **已实施** —— `X-API-Key` 分桶加验签（本文件 ⚠️① 的修复） |
| `docs/说明/测试.md` §六 | 覆盖缺口：「**前者间接**、后者零覆盖」 |
| `api/test_rag_search.py:15` | ⚠️ 上面 ⚠️③ 那条实测的**原始出处** —— **它一直在仓里** |

> ### ✅ 三条"要不要做"—— **2026-09-30 业务方已裁**
>
> | # | 问题 | 裁定 | 落点 |
> |---|---|---|---|
> | **1** | **该不该给桶加 `EXPIRE`？** | ✅ **要** | `is_allowed` 的 Lua 里加 `redis.call('EXPIRE', KEYS[1], <TTL>)`<br>⚠️ **TTL 取多少？** 桶的语义是"回满即无意义" ⇒ 建议 `capacity/rate` 的若干倍；⬜ **具体值待定** |
> | **2** | **Redis 不通时 fail-open 还是 fail-closed？** | ✅ **已裁：fail-open + 必须响的日志**（业务方 2026-09-30 同意） | `is_allowed` / `get_limit_info` / `get_remaining` 三处各包 `except redis.RedisError` ⇒ **放行 + `logger.error`** |
> | **3** | **限流参数该不该收进 `token_config.py`？** | ✅ **要进** | `global_limiter` / `user_limiter` 的 `rate` / `capacity` 改从 `token_config` 取<br>⚠️ **`token_config.py` 还没建**（那是计划 ①a 的 Task 2）⇒ **本条并进 ①a 的 Task 2**，⛔ 别另开一轮 |
>
> #### 🔵 ② 的理由（我方建议的完整论证，⬜ 待点头）
>
> | 维度 | 说明 |
> |---|---|
> | **① 限流是"保护"，不是"边界"** | 本仓的**安全边界是 `deps.py` 的鉴权**（那里 fail-closed **是对的**）⇒ ⛔ 混起来会把"**保护措施失效**"升级成"**服务不可用**" |
> | **② 代价差一个量级** | **fail-closed（现状）**：Redis 抖 3 秒 ⇒ **全站 3 秒 500**<br>**fail-open**：Redis 抖 3 秒 ⇒ **限流失效 3 秒** |
> | **③ 与同族对齐** | `token_tracker` 是**有意的 fail-open 且写了理由**；这边是**无意中的 fail-closed 且没写理由** |
> | **④ 配一条** | ⚠️ **`logger.error` 要响** —— 否则"限流悄悄失效"没人知道（另一种「**静默降级比报错更危险**」） |
>
> **⚠️ 一个例外**：`global_limiter` fail-open ⇒ **过载保护也失效**。
> Redis 挂了 **且** 流量暴涨 ⇒ 雪上加霜。**但仍选 fail-open** —— 低概率叠加 vs **确定的全站 500**。
