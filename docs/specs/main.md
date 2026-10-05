# `api/main.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 应用装配 + **3 条中间件** + 全局异常处理 + 看板挂载<br>✅ 2026-09-30 起**限流分桶会验签了**（修 `B9-b`）· ✅ **4 处错误文案已修 + 加了 `retry_after`**（修 `B12`）<br>🔴 **2026-10-03（`①b` Task 6 · `DEC-046`）：`QuotaMiddleware` 的额度口径从「每日请求【次数】」换成「按用户按天 **token**」**（= `R1.3`）。 |
| **对外提供** | `app`（FastAPI 实例）· `MIDDLEWARE_EXEMPT_PATHS`（`:118` · 🔴 **2026-10-05 由 `PUBLIC_PATHS` 改名**，见下）· `resolve_rate_limit_identity()`（`:126`）<br>🔵 2026-10-03 新增三个**配额判定件**：`_next_day_reset_ts()`（`:249`）· `quota_reject_payload(info)`（`:256`）· `quota_headers(info)`（`:284`）—— **纯函数，不连 DB/Redis 就能单测** |
| **谁在用** | 服务入口（uvicorn `main:app`）· ⚠️ **几乎每个测试**都经 `api/conftest.py` 的 `from main import app` |
| **规模** | 651 行 |

## ✅ 做了什么

- **装配**：挂载各 router（`api_v1` / `api_v1_rag` / `api_v1_agent` / …）、中间件、异常处理器、Gradio 看板（`/dashboard`，`ENABLE_DASHBOARD` 门控）
- **3 条中间件**（执行顺序见下方 ⚠️ 节）
  · `QuotaMiddleware`（`:287`）—— **按【用户】【每天】的 token 预算**判定（数据源 `token_tracker.get_token_budget_info`），
    超了返 **429 + `QUOTA_EXCEEDED`**，并给三个响应头 `X-Quota-Limit` / `X-Quota-Remaining` / `X-Quota-Reset`
    （🔴 **2026-10-03 起语义是 token、不再是次数**）。
- **中间件豁免名单** `MIDDLEWARE_EXEMPT_PATHS`（`:118`，11 条）——
  🔴 **2026-10-05 由 `PUBLIC_PATHS` 改名**（`DEC-074`）：旧名说"公开"，而它的真实语义是
  「**跳过限流 / 配额两个中间件**」，与"该端点要不要鉴权"**无关**。
  ⚠️ 现成反例就写在名单里：`/api/v1/admin/create_user` **在名单内，却要 `require_admin`**（`api_v1.py:161`）。
  ⛔ 判断一条端点"公不公开"，**别读这个名单** —— 跑 `scripts/check_route_auth.py`。
- **全局异常处理器**（`:362` 起）

## 🟡 做到哪 / 缺什么

- ✅ ~~🔴 **4 处错误文案不准确**~~ ⇒ **2026-10-01 已修**（`B12` · **①a Task 1**）：限流 429 那处原写
  「Internal server error」（**说反了**）⇒ 改成说清"是限流"；`/health` 与 `/ready` ×2 的 **503** 改成
  「服务尚未就绪」；⛔ **全局 500 处理器不动**（它真的是内部错误）。
  另新增 `AppException.retry_after`（**可选**，不挂就不写字段）+ 响应头 `Retry-After`。
  📄 回归：`api/test_error_contract.py`（5 条）
- 🔴 **X-API-Key 现在每个请求查库 2 次**（两条中间件各一次）—— 2026-09-30 修 `B9-b` 后新增的一次。
  ⬜ 可选优化：`request.state` 缓存后复用。**未做**（YAGNI）
- ⚠️ **配额那一层每个请求多一次 DB 查询**（2026-10-03 起）—— 原先次数那套是 Redis `INCR`，
  现在走 `get_daily_token_usage`（`SELECT SUM(...) ... WHERE created_at >= CURRENT_DATE`）。
  **口径不同 ⇒ 无法用同一个计数器表达**；增量与 `B11` 熔断（也已每请求一次 `SUM`）**同量级**。
- ⬜ **`TextNormalizationMiddleware`（`:293`）未核** —— 本 spec 只核了另两条
- ⬜ 零散的 `on_event` 弃用告警（`:512` / `:526`，FastAPI 建议改 lifespan）—— `ROADMAP` 待办 **T4** 的一类

## ⚠️ 看代码会误判的地方 ⭐

> 本节是这份 spec **最该读的部分** —— 前两节读代码也能推出来，**只有本节推不出来**。

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`resolve_rate_limit_identity()` 是在鉴权」** | ⛔ **不是**。它**只算【限流桶名】** —— 验签失败**不拦请求**，只是**让它落匿名桶**。<br>**真正的鉴权在 `api/deps.py:35`**（那里才会抛 `AUTH_EXPIRED`）。<br>⚠️ **两者混起来看会得出"验了签就安全了"的错误结论。** |
| 🔴 **「`MIDDLEWARE_EXEMPT_PATHS` 里的路径 = 不需要登录」** | ⛔ **不是**。它只表示**跳过两条中间件**（限流 + 配额）。<br>**该端点要不要鉴权，由它自己的依赖（`Depends(get_current_user)`）决定** —— **两回事**。<br>📌 **2026-10-05 前它叫 `PUBLIC_PATHS`** —— 那个名字**正是在犯这个错**（`DEC-074`）。<br>📌 判据：`scripts/check_route_auth.py`（跑它，⛔ 别读名单）。 |
| 🔴 **「两条中间件拦得住匿名」** | ⛔ **拦不住，也不该由它们拦**。<br>① 中间件拿到 key 也**得查库**才知道有没有效 ⇒ 让它们"拒绝匿名" = **把鉴权抄第二份**（`DEC-051` 那一族）；<br>② 且**匿名口子是开着的**（`B9`）—— 在这里拒会把匿名入口一起关掉，那是另一个决定。<br>⇒ **鉴权与错误码在路由依赖那一层**：`AUTH_MISSING`（`deps.py:65`）· `AUTH_EXPIRED`（`deps.py:38/:50`）。<br>⚠️ 实测（`httpx.ASGITransport`，不带凭据打 4 条非豁免端点）⇒ **一律 `401 AUTH_MISSING`**，干净。 |
| 🔴 **「`check_route_auth.py` 覆盖了所有路由」** | ⛔ **2026-10-05 前它只认 `APIRoute`** ⇒ `/api/v1/ws/agent`（**真花钱、真没鉴权**）**零输出**。<br>⇒ 本轮补上（`DEC-074`）：WS 也进清单，标签是 `WS`。基线 **1 → 3 条**。<br>⚠️ 但**中间件仍然管不到 WS**（`BaseHTTPMiddleware` 只处理 `scope["type"]=="http"`）——<br>「进清单」≠「被保护」，它只是**从看不见变成看得见**。 |
| 🔴 **「中间件按代码里 `add_middleware` 的顺序执行」** | ⛔ **正好相反**。Starlette 里**后加的在外层** ⇒ **最后写的先跑**。<br>**实测（`app.user_middleware` 索引 0 = 最外层）**：<br>`TextNormalizationMiddleware` → `QuotaMiddleware` → `RateLimitMiddleware`<br>⛔ 而代码里的**书写**顺序是 RateLimit（`:212`）→ Quota（`:286`）→ TextNormalization（`:343`）。 |
| ⚠️ **「限流和配额在同一处处理，不会不一致」** | ⛔ **历史上就不一致过** —— 到 2026-09-30 为止，`QuotaMiddleware`（`:233`）**验签**、`RateLimitMiddleware`（原 `:141`）**不验**。<br>⇒ 编个 `X-API-Key` 就能拿**独立限流桶**。**已修（`B9-b`）**，但**"同一件事写两遍"这个形态还在**。 |
| ✅ **「`"error": "Internal server error"` 只出现一次」** | **2026-10-01 前**：全文 **5 处**，**且不是都对**（`:158` 限流 429 **说反了** · `:460/:481/:496` **503** 也不准 · `:364` 全局 500 **是对的**）。<br>**现状**：只剩 `:364` 那处**故意保留**（它真的是内部错误）。<br>📌 **本行是 `B12` 落点数从 1 更正为 4 的依据** —— 而**判据现在是可打印的**：<br>`grep -n '"error": "Internal server error"' api/main.py` ⇒ 应只有 1 行（500 处理器） |
| ⚠️ **「`/metrics` 和 `/health` 受保护」** | ⛔ **被 `MIDDLEWARE_EXEMPT_PATHS` 豁免** ⇒ **绕过限流与配额**（**故意**的：否则 K8s/Docker 探针会被 429 打成不健康）<br>⚠️ **代价**：`/metrics` 可被无限刷。**已登记未做**（`B9-b` 风险说明） |
| 🔴 **「`X-Quota-Limit` 说的是调用次数」** | ⛔ **2026-10-03 起它说的是【每天多少 token】**（头名**故意没改** —— 客户端已在读，改名的破坏面比改语义大）。<br>`X-Quota-Reset` 仍是**次日 0 点的 Unix 时间戳**（日预算由 SQL 的 `created_at >= CURRENT_DATE` 翻页）。 |
| 🔴 **「配额那层拦不住就拒服务（fail-closed）」** | ⛔ **它是 fail-open 的** —— `get_daily_token_usage` **查库失败 ⇒ 退回内存缓存值 ⇒ 放行**。<br>**与 `B8` / `B10` 同取向**（额度是**成本控制**，不是安全边界）。<br>⛔ **别"顺手统一"成 `deps.py` 鉴权那套 fail-closed** —— 两者**故意不同**。 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/token_tracker.md` | **配额**那一层的数据源（`get_token_budget_info`）—— 本文件只负责在中间件里消费它 |
| `docs/specs/归档/quota_limiter.md` | ⚰️ **已归档** —— 原先的「每日**次数**」计数器，**2026-10-03 随 `DEC-046` 删除** |
| `后端补齐清单` **B9-b** | 限流分桶加验签（**2026-09-30 已做**） |
| `后端补齐清单` **B12** | 错误文案 + `retry_after`（⚠️ **本文把落点从 1 处更正为 4 处**） |
| `api/test_rate_limit_identity.py` | `resolve_rate_limit_identity` 的 7 条回归测试 |
| `api/test_public_paths.py` | `MIDDLEWARE_EXEMPT_PATHS` 与真实路由的一致性 |
| `api/test_route_auth_scan.py` | **改名与接线那一轮的判据**（`DEC-074`）—— 9 条：扫描口径必须**看得见 WS**、纯函数**不许 `chdir`**、**自证**旧口径扫不到 WS |
| `scripts/check_route_auth.py` | ⭐ **「哪些路由没鉴权」的权威判据** —— ⛔ **别读名单、读它**（现含 WS） |
| `DEC-074` | 改名 + **把上面那个脚本真的接进 CI 与提交门**（此前它**哪都没跑**） |
