# `api/main.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 应用装配 + **3 条中间件** + 全局异常处理 + 看板挂载<br>✅ 2026-09-30 起**限流分桶会验签了**（修 `B9-b`）· ✅ **4 处错误文案已修 + 加了 `retry_after`**（修 `B12`） |
| **对外提供** | `app`（FastAPI 实例）· `PUBLIC_PATHS`（`:107`）· `resolve_rate_limit_identity()`（`:115`） |
| **谁在用** | 服务入口（uvicorn `main:app`）· ⚠️ **几乎每个测试**都经 `api/conftest.py` 的 `from main import app` |
| **规模** | 609 行 |

## ✅ 做了什么

- **装配**：挂载各 router（`api_v1` / `api_v1_rag` / `api_v1_agent` / …）、中间件、异常处理器、Gradio 看板（`/dashboard`，`ENABLE_DASHBOARD` 门控）
- **3 条中间件**（执行顺序见下方 ⚠️ 节）
- **公开路径豁免名单** `PUBLIC_PATHS`（`:107`，11 条）
- **全局异常处理器**（`:362` 起）

## 🟡 做到哪 / 缺什么

- ✅ ~~🔴 **4 处错误文案不准确**~~ ⇒ **2026-10-01 已修**（`B12` · **①a Task 1**）：限流 429 那处原写
  「Internal server error」（**说反了**）⇒ 改成说清"是限流"；`/health` 与 `/ready` ×2 的 **503** 改成
  「服务尚未就绪」；⛔ **全局 500 处理器不动**（它真的是内部错误）。
  另新增 `AppException.retry_after`（**可选**，不挂就不写字段）+ 响应头 `Retry-After`。
  📄 回归：`api/test_error_contract.py`（5 条）
- 🔴 **X-API-Key 现在每个请求查库 2 次**（两条中间件各一次）—— 2026-09-30 修 `B9-b` 后新增的一次。
  ⬜ 可选优化：`request.state` 缓存后复用。**未做**（YAGNI）
- ⬜ **`TextNormalizationMiddleware`（`:293`）未核** —— 本 spec 只核了另两条
- ⬜ 零散的 `on_event` 弃用告警（`:512` / `:526`，FastAPI 建议改 lifespan）—— `ROADMAP` 待办 **T4** 的一类

## ⚠️ 看代码会误判的地方 ⭐

> 本节是这份 spec **最该读的部分** —— 前两节读代码也能推出来，**只有本节推不出来**。

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`resolve_rate_limit_identity()` 是在鉴权」** | ⛔ **不是**。它**只算【限流桶名】** —— 验签失败**不拦请求**，只是**让它落匿名桶**。<br>**真正的鉴权在 `api/deps.py:35`**（那里才会抛 `AUTH_EXPIRED`）。<br>⚠️ **两者混起来看会得出"验了签就安全了"的错误结论。** |
| 🔴 **「`PUBLIC_PATHS` 里的路径 = 不需要登录」** | ⛔ **不是**。它只表示**跳过两条中间件**（限流 + 配额）。<br>**该端点要不要鉴权，由它自己的依赖（`Depends(get_current_user)`）决定** —— **两回事**。 |
| 🔴 **「中间件按代码里 `add_middleware` 的顺序执行」** | ⛔ **正好相反**。Starlette 里**后加的在外层** ⇒ **最后写的先跑**。<br>**实测（`app.user_middleware` 索引 0 = 最外层）**：<br>`TextNormalizationMiddleware` → `QuotaMiddleware` → `RateLimitMiddleware`<br>⛔ 而代码里的**书写**顺序是 RateLimit（`:212`）→ Quota（`:286`）→ TextNormalization（`:343`）。 |
| ⚠️ **「限流和配额在同一处处理，不会不一致」** | ⛔ **历史上就不一致过** —— 到 2026-09-30 为止，`QuotaMiddleware`（`:233`）**验签**、`RateLimitMiddleware`（原 `:141`）**不验**。<br>⇒ 编个 `X-API-Key` 就能拿**独立限流桶**。**已修（`B9-b`）**，但**"同一件事写两遍"这个形态还在**。 |
| ✅ **「`"error": "Internal server error"` 只出现一次」** | **2026-10-01 前**：全文 **5 处**，**且不是都对**（`:158` 限流 429 **说反了** · `:460/:481/:496` **503** 也不准 · `:364` 全局 500 **是对的**）。<br>**现状**：只剩 `:364` 那处**故意保留**（它真的是内部错误）。<br>📌 **本行是 `B12` 落点数从 1 更正为 4 的依据** —— 而**判据现在是可打印的**：<br>`grep -n '"error": "Internal server error"' api/main.py` ⇒ 应只有 1 行（500 处理器） |
| ⚠️ **「`/metrics` 和 `/health` 受保护」** | ⛔ **被 `PUBLIC_PATHS` 豁免** ⇒ **绕过限流与配额**（**故意**的：否则 K8s/Docker 探针会被 429 打成不健康）<br>⚠️ **代价**：`/metrics` 可被无限刷。**已登记未做**（`B9-b` 风险说明） |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/quota_limiter.md` | **配额**那一层（本文件只负责装配它） |
| `后端补齐清单` **B9-b** | 限流分桶加验签（**2026-09-30 已做**） |
| `后端补齐清单` **B12** | 错误文案 + `retry_after`（⚠️ **本文把落点从 1 处更正为 4 处**） |
| `api/test_rate_limit_identity.py` | `resolve_rate_limit_identity` 的 7 条回归测试 |
| `api/test_public_paths.py` | `PUBLIC_PATHS` 与真实路由的一致性 |
