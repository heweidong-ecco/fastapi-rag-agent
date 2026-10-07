# `api/main.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用** —— 应用装配 + **3 条中间件** + 全局异常处理 + 看板挂载 + **3 条页面路由**<br>✅ 2026-09-30 起**限流分桶会验签了**（修 `B9-b`）· ✅ **4 处错误文案已修 + 加了 `retry_after`**（修 `B12`）<br>🔴 **2026-10-03（`①b` Task 6 · `DEC-046`）：`QuotaMiddleware` 的额度口径从「每日请求【次数】」换成「按用户按天 **token**」**（= `R1.3`）。<br>🔴 **2026-10-05（批 3 · `N9`）：两条中间件在【依赖不可用】时都改为 fail-open** —— 限流侧身份 `None` ⇒ 跳过用户级限流；额度侧身份 `None` ⇒ 跳过额度检查（`DEC-079`）。<br>🆕 **2026-10-06（`DEC-088` · `F1`）：新增第二条页面路由 `GET /approvals`** —— 与 `/chat` **逐条同构**（302 · `include_in_schema=False` · 显式进无鉴权基线 · 各 3 条页面用例）。<br>🔵 **2026-10-06（`DEC-090` · `F4` 第三条）：异常处理器多写一个【可选】`scope`**（与 `retry_after` 同套路，见「做到哪」）。<br>🆕 **2026-10-06（`DEC-093` · `F2`）：新增第三条页面路由 `GET /trace`** → 302 `/static/web/trace.html` —— 同样与 `/chat` 同构，但**它的页面用例是 6 条不是 3 条**（多出 3 条页面坏法的守卫，见「做到哪」）。<br>🔧 **2026-10-06（`DEC-094`）：页面路由【代码本身没动】** —— 本份记的是 `approvals.html` 的 4 条 URL 前缀与 `ci.yml` 的 `node --test`，**两条都不在这个模块里**；⚠️ 唯一相关的是「页面守卫从"盯一个页面"改成"盯全站"」⇒ 见「看代码会误判」。 |
| **对外提供** | `app`（FastAPI 实例）· `MIDDLEWARE_EXEMPT_PATHS`（**:118** · 🔴 **2026-10-05 由 `PUBLIC_PATHS` 改名**，见下）· `resolve_rate_limit_identity()`（**:126**）<br>🔵 2026-10-03 新增三个**配额判定件**：`_next_day_reset_ts()`（**:322**）· `quota_reject_payload(info)`（**:329**）· `quota_headers(info)`（**:357**）—— **纯函数，不连 DB/Redis 就能单测**<br>🔵 **2026-10-05 新增** `resolve_quota_identity()`（**:180**）—— 同上理由抽出来的纯函数（`QuotaMiddleware` 那段的身份解析，原先**内联在 `dispatch` 里、没法单测**）<br>🆕 **2026-10-06 新增三条页面路由**：`GET /chat`（**:538**）→ 302 `/static/web/chat.html` · **`GET /approvals`（`:547`）→ 302 `/static/web/approvals.html`**（接管页）· **`GET /trace`（`:559`）→ 302 `/static/web/trace.html`**（Trace 页）—— 三条都是 `include_in_schema=False` |
| **谁在用** | 服务入口（uvicorn `main:app`）· ⚠️ **几乎每个测试**都经 `api/conftest.py` 的 `from main import app` |
| **规模** | 🔴 **别写死行数** —— 跑 `wc -l api/main.py`（2026-10-06 加 `/trace` 后为 **771**；此前 752 / 733 = 2026-10-05，651 = 更早）<br>⚠️ **本节行号同理，改完必须重取** —— 2026-10-05 那次编辑把旧行号**全部**打歪过一次；**2026-10-06 加 `/approvals` 后重取了一遍**（实测漂了的：`on_event` 那处 `:656`/`:673` ⇒ 实为 **`:675`/`:692`**）。<br>🆕 **2026-10-06 加 `/trace` 后重取**：本文里 **`:538`（`/chat`）· `:547`（`/approvals`）· `:559`（`/trace`）· `:476`/`:495`（异常处理器）** 均为**当次实测的【装饰器行】**。<br>🔴 **顺带纠正一处**：本节此前写的 `/chat` `:531` · `/approvals` `:540` **是旧值**（`DEC-090` 加异常处理器的 `scope` 之后整体下移了 7 行）—— 而 **`docs/specs/static_frontend.md` 里写的 `:538`/`:547` 才是对的**（两份文档**互相矛盾**，已统一）。⚠️ 这类"两份文档各记一个行号"是本仓的老形态 ⇒ **判据一律现取**：`grep -n '@app.get("/' api/main.py`。 |

## ✅ 做了什么

- **装配**：挂载各 router（`api_v1` / `api_v1_rag` / `api_v1_agent` / …）、中间件、异常处理器、Gradio 看板（`/dashboard`，`ENABLE_DASHBOARD` 门控）
- **3 条中间件**（执行顺序见下方 ⚠️ 节）
  · `QuotaMiddleware`（`:371`）—— **按【用户】【每天】的 token 预算**判定（数据源 `token_tracker.get_token_budget_info`），
    超了返 **429 + `QUOTA_EXCEEDED`**，并给三个响应头 `X-Quota-Limit` / `X-Quota-Remaining` / `X-Quota-Reset`
    （🔴 **2026-10-03 起语义是 token、不再是次数**）。
    🔴 **2026-10-05（批 3 · `N9`）**：身份解析抽成 `resolve_quota_identity()`；
    **库不可用时 ⇒ 身份为 `None` ⇒ 跳过额度检查（fail-open）+ ERROR 日志** —— 见 ⚠️ 节末行。
- **中间件豁免名单** `MIDDLEWARE_EXEMPT_PATHS`（`:118`，11 条）——
  🔴 **2026-10-05 由 `PUBLIC_PATHS` 改名**（`DEC-074`）：旧名说"公开"，而它的真实语义是
  「**跳过限流 / 配额两个中间件**」，与"该端点要不要鉴权"**无关**。
  ⚠️ 现成反例就写在名单里：`/api/v1/admin/create_user` **在名单内，却要 `require_admin`**（`api_v1.py:161`）。
  ⛔ 判断一条端点"公不公开"，**别读这个名单** —— 跑 `scripts/check_route_auth.py`。
- **全局异常处理器**（`:476` / `:495`）
- 🔵 **2026-10-06（`DEC-085` 裁定 #10）：新增 `GET /chat` → 302 `/static/web/chat.html`**（`:538`）
  —— 本仓**第一条面向人的页面路由**（此前 `/` 返回的是 JSON 服务索引，不是页面）。
  ⚠️ `include_in_schema=False`（它不是 API，⛔ 不进 openapi）· ⚠️ 302 而**不是**直接返回文件
  （页面本体由已挂的 `/static` 托管：零 CORS、零新服务、零构建）。
  🔴 **它是一条【新的公开路由】** ⇒ 会让 `scripts/check_route_auth.py --baseline` 报"多了一条"
  ⇒ **已显式写进 `scripts/route-auth-baseline.txt`**（一次有意识的操作，⛔ 不是顺手刷基线）。
  📌 守卫：`api/test_chat_page.py` **3 条**（跳转目标正确 / 目标文件真在磁盘上且是 `text/html` / **不在 openapi 里**）
  —— ⚠️ 最后那条是必需的：`check_route_auth.py --baseline` **抓不到"路由被删"**
  （它会把少掉的那条报成"少了 1 条（修好了）"并 `exit 0`）。
- 🔵 **2026-10-06（`DEC-088` §3.3 · `F1`）：新增 `GET /approvals` → 302 `/static/web/approvals.html`**（`:547`）
  —— **第二条页面路由**，形状与 `/chat` **逐条同构**（`include_in_schema=False` · 302 而非直接返回文件 ·
  **显式写进 `scripts/route-auth-baseline.txt`**）。
  📌 守卫：`api/test_approvals_page.py` **3 条**（同 `/chat` 那三条）。
- 🔵 **2026-10-06（`DEC-093` · `F2`）：新增 `GET /trace` → 302 `/static/web/trace.html`**（`:559`）
  —— **第三条页面路由**，形状仍与 `/chat` 同构（`include_in_schema=False` · 302 · 显式进基线）。
  🔴 **但它的守卫是 6 条，不是 3 条** —— 除了照抄的那三条，另有 **3 条专治页面的坏法**：
  · `test_page_builds_urls_via_the_tested_helper` · `test_page_loads_the_trace_script` ·
    `test_page_does_not_print_the_two_dead_overview_cards`
  ⚠️ **曾经还有第 4 条**（`test_page_url_literals_carry_the_api_prefix`）——
     🔴 **2026-10-06 已搬去 `api/test_web_pages.py`**，因为它**只盯 `trace.html` 一个文件**，
     而**"只盯一个页面的门挡不住下一个页面"正是它当初没拦住 `approvals.html` 的原因**。
     ⇒ 现在那条守卫**扫 `api/static/` 下每一个 `.html`**（`DEC-094` §三·A）。
  ⚠️ **为什么需要这一类守卫**：`F1` 的 `approvals.html` 里 **4 条 URL 全少 `/api/v1`** ⇒ 页面 100% 不可用，
    而**当时三层判据一条都不会红**（页面用例只看 302、JS 用例只测纯函数、路由门只管后端）。
    📄 事故全文与"为什么漏"⇒ `DEC-093` §四。✅ **2026-10-06 已修**（业务方裁「并进 `F2` 的 PR」）⇒ `DEC-094`。
  ⚠️ **当时的代价（记账）**：`api/static/trace_viewer.html` 那时**没有删** —— `docs/FAQ.md` 写过它的地址，
    删掉会让那条指引落到 404；只在它顶部加了一条指向 `/trace` 的横幅。
    🔴 **2026-10-07 改了做法**（`DEC-096` · `F5`）：**两个存量坏页都删掉**，并**在同一次改动里改掉
    `FAQ.md` 那条旧地址** —— 即「指引落到 404」这件事**用改指引解决**，⛔ 不是靠留一个坏页兜着。

## 🟡 做到哪 / 缺什么

- ✅ ~~🔴 **4 处错误文案不准确**~~ ⇒ **2026-10-01 已修**（`B12` · **①a Task 1**）：限流 429 那处原写
  「Internal server error」（**说反了**）⇒ 改成说清"是限流"；`/health` 与 `/ready` ×2 的 **503** 改成
  「服务尚未就绪」；⛔ **全局 500 处理器不动**（它真的是内部错误）。
  另新增 `AppException.retry_after`（**可选**，不挂就不写字段）+ 响应头 `Retry-After`。
  📄 回归：`api/test_error_contract.py`（5 条）
- 🔵 **2026-10-06（`DEC-090` · `F4` 第三条）：全局处理器多写一个【可选】`scope` 字段** ——
  `app_exception_handler` 里 `getattr(exc, "scope", None)` 非 `None` 才写进 body，
  **与 `retry_after` 逐字同套路**（⛔ 不给默认值 —— 兜一个 `"global"` 会让**中间件的限流 429**
  （根本没有日级额度）也长出「明日起恢复」来）。用途：`R3.2` 的前端熔断卡片要分清
  「全站级 / 会话级」两种额度，而两者 `ErrorCode` **都是 `QUOTA_EXCEEDED`**、分不出来。
  ⚠️ **只有对话页那条链**（`api_v1_rag.stream_search`）的 429 带了它 —— 其余 **33 处**
  `raise` **有意没接**（bounded）。
- 🔴 **X-API-Key 现在每个请求查库 2 次**（两条中间件各一次）—— 2026-09-30 修 `B9-b` 后新增的一次。
  ⬜ 可选优化：`request.state` 缓存后复用。**未做**（YAGNI）
- ⚠️ **配额那一层每个请求多一次 DB 查询**（2026-10-03 起）—— 原先次数那套是 Redis `INCR`，
  现在走 `get_daily_token_usage`（`SELECT SUM(...) ... WHERE created_at >= CURRENT_DATE`）。
  **口径不同 ⇒ 无法用同一个计数器表达**；增量与 `B11` 熔断（也已每请求一次 `SUM`）**同量级**。
- ⬜ **`TextNormalizationMiddleware`（`:423`）未核** —— 本 spec 只核了另两条
- ⬜ 零散的 `on_event` 弃用告警（`:675` / `:692`，FastAPI 建议改 lifespan）—— `ROADMAP` 待办 **T4** 的一类
- ⬜ **`X-API-Key` 每请求查库 2 次**（上面那条）**在库不可用时变成"两次都要探一次库"** ——
  2026-10-05 起两处都 fail-open，所以**只是慢**，⛔ 不再是 500（`N9`）。

## ⚠️ 看代码会误判的地方 ⭐

> 本节是这份 spec **最该读的部分** —— 前两节读代码也能推出来，**只有本节推不出来**。

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`resolve_rate_limit_identity()` 是在鉴权」** | ⛔ **不是**。它**只算【限流桶名】** —— 验签失败**不拦请求**，只是**让它落匿名桶**。<br>**真正的鉴权在 `api/deps.py`**（那里才会抛 `AUTH_EXPIRED`）。<br>⚠️ **两者混起来看会得出"验了签就安全了"的错误结论。**<br>🔴 **2026-10-05（`N9`）它多了一种返回值 `None`** —— 含义是「**判不了**」（认证服务不可用），⛔ **不是 `"anonymous"`**（「判了，就是匿名」）。中间件见 `None` 会**跳过用户级限流**。 |
| 🔴 **「`resolve_quota_identity()` 和限流那个应该长得一样」** | ⛔ **故意不一样** —— 两者在"库挂了"时的**出口不同**：<br>· 限流那个返回 `None` ⇒ 中间件**跳过用户级限流**（不落匿名桶）；<br>· 额度那个返回 `None` ⇒ 走 `QuotaMiddleware` **本来就有**的"未识别身份 ⇒ 原样放行"。<br>⚠️ **两边都是 fail-open**，但**落点不同**；⛔ 别为"看着统一"把它们的返回类型合并。<br>📄 四层分工（含 `deps.py` 的 fail-closed）⇒ `DEC-079` |
| 🔴 **「`MIDDLEWARE_EXEMPT_PATHS` 里的路径 = 不需要登录」** | ⛔ **不是**。它只表示**跳过两条中间件**（限流 + 配额）。<br>**该端点要不要鉴权，由它自己的依赖（`Depends(get_current_user)`）决定** —— **两回事**。<br>📌 **2026-10-05 前它叫 `PUBLIC_PATHS`** —— 那个名字**正是在犯这个错**（`DEC-074`）。<br>📌 判据：`scripts/check_route_auth.py`（跑它，⛔ 别读名单）。 |
| 🔴 **「两条中间件拦得住匿名」** | ⛔ **拦不住，也不该由它们拦**。<br>① 中间件拿到 key 也**得查库**才知道有没有效 ⇒ 让它们"拒绝匿名" = **把鉴权抄第二份**（`DEC-051` 那一族）；<br>② 且**匿名口子是开着的**（`B9`）—— 在这里拒会把匿名入口一起关掉，那是另一个决定。<br>⇒ **鉴权与错误码在路由依赖那一层**：`AUTH_MISSING`（`deps.py:65`）· `AUTH_EXPIRED`（`deps.py:38/:50`）。<br>⚠️ 实测（`httpx.ASGITransport`，不带凭据打 4 条非豁免端点）⇒ **一律 `401 AUTH_MISSING`**，干净。 |
| 🔴 **「`check_route_auth.py` 覆盖了所有路由」** | ⛔ **2026-10-05 前它只认 `APIRoute`** ⇒ `/api/v1/ws/agent`（**真花钱、真没鉴权**）**零输出**。<br>⇒ 本轮补上（`DEC-074`）：WS 也进清单，标签是 `WS`。基线 **1 → 3 条**。<br>⚠️ 但**中间件仍然管不到 WS**（`BaseHTTPMiddleware` 只处理 `scope["type"]=="http"`）——<br>「进清单」≠「被保护」，它只是**从看不见变成看得见**。 |
| 🔴 **「中间件按代码里 `add_middleware` 的顺序执行」** | ⛔ **正好相反**。Starlette 里**后加的在外层** ⇒ **最后写的先跑**。<br>**实测（`app.user_middleware` 索引 0 = 最外层）**：<br>`TextNormalizationMiddleware` → `QuotaMiddleware` → `RateLimitMiddleware`<br>⛔ 而代码里的**书写**顺序是 RateLimit（`:305`）→ Quota（`:416`）→ TextNormalization（`:473`）。<br>⚠️ 这些行号**随每次编辑漂** —— 权威判据是打印式的：`grep -n '^app.add_middleware' api/main.py` |
| ⚠️ **「限流和配额在同一处处理，不会不一致」** | ⛔ **历史上就不一致过** —— 到 2026-09-30 为止，`QuotaMiddleware` **验签**、`RateLimitMiddleware` **不验**。<br>⇒ 编个 `X-API-Key` 就能拿**独立限流桶**。**已修（`B9-b`）**，但**"同一件事写两遍"这个形态还在**。<br>🔴 **2026-10-05 又是一例**：批 3 给两边各加了一处 `except`，**取向相同而落点不同**（见上方 `resolve_quota_identity` 那行）。 |
| ✅ **「`"error": "Internal server error"` 只出现一次」** | **2026-10-01 前**：全文 **5 处**，**且不是都对**（限流 429 那处 **说反了** · 三处 **503** 也不准 · 全局 500 **是对的**）。<br>**现状**：只剩 **1 行**（`:502`，在全局 500 处理器里）**故意保留** —— 它真的是内部错误。<br>📌 **本行是 `B12` 落点数从 1 更正为 4 的依据** —— 而**判据现在是可打印的**：<br>`grep -n '"error": "Internal server error"' api/main.py` ⇒ 应只有 1 行 |
| ⚠️ **「`/metrics` 和 `/health` 受保护」** | ⛔ **被 `MIDDLEWARE_EXEMPT_PATHS` 豁免** ⇒ **绕过限流与配额**（**故意**的：否则 K8s/Docker 探针会被 429 打成不健康）<br>⚠️ **代价**：`/metrics` 可被无限刷。**已登记未做**（`B9-b` 风险说明） |
| 🔴 **「`X-Quota-Limit` 说的是调用次数」** | ⛔ **2026-10-03 起它说的是【每天多少 token】**（头名**故意没改** —— 客户端已在读，改名的破坏面比改语义大）。<br>`X-Quota-Reset` 仍是**次日 0 点的 Unix 时间戳**（日预算由 SQL 的 `created_at >= CURRENT_DATE` 翻页）。 |
| 🔴 **「配额那层拦不住就拒服务（fail-closed）」** | ⛔ **它是 fail-open 的** —— `get_daily_token_usage` **查库失败 ⇒ 退回内存缓存值 ⇒ 放行**。<br>**与 `B8` / `B10` 同取向**（额度是**成本控制**，不是安全边界）。<br>⛔ **别"顺手统一"成 `deps.py` 鉴权那套 fail-closed** —— 两者**故意不同**。 |
| ⚠️ **「`/` 也是一个页面（或 `/chat` 与 `/` 是一回事）」** | ⛔ **不是**。**`/` 返回 JSON**（`{"status":"ok","services":{…}}` —— 一个**服务索引**，给人看有哪些 API 前缀），**`/chat` / `/approvals` / `/trace` 才是页面**。<br>四条都**不在 openapi 里**（`/` 是普通 JSON 路由、那三条页面路由显式 `include_in_schema=False`）⇒ ⛔ **别因为"都查不到"就把它们当一类**。<br>⚠️ **别想着把 `/` 改成跳转对话页** —— 那条是**线上契约**（已有人/脚本在读那个 JSON）。 |
| ⚠️ **「`/chat` / `/approvals` / `/trace` 在路由基线里 ⇒ 它们被门保护着」** | ⛔ **基线只记录"有这条且无鉴权依赖"，⛔ 不防它被删**。<br>`check_route_auth.py --baseline` 见到**少一条**会报「少了 N 条（修好了）」并 **`exit 0`** ⇒ **删掉 `/approvals` 全绿**。<br>⇒ 真正的守卫是页面用例：`api/test_chat_page.py` / `api/test_approvals_page.py` **各 3 条**，`api/test_trace_page.py` **6 条**（含"路由必须 302 到对应的那个 HTML"）。 |
| 🔴🔴 **「页面能 302 过去 ⇒ 这个页面就能用」** | ⛔ **两件事** —— `F1` 的 `approvals.html` 实测：**302 正确、目标文件在磁盘上、不在 openapi 里**（三条用例全绿），**而页面在浏览器里 100% 打不开** —— 它 fetch 的 **4 条 URL 全少 `/api/v1`**。<br>⚠️ **三层判据一条都没红**：页面用例只看 302 · JS 用例全是**纯函数**（前缀不经过它们）· 路由门只管**后端有没有多余的无鉴权路由**。<br>⇒ **补了第 4 类守卫：读页面源码，把里面 `getJSON(...)` / `fetch(...)` 的字符串字面量抠出来，必须以 `/api/v1` 开头**。<br>🔴 **⚠️ 它现在在 `api/test_web_pages.py`，不在 `test_trace_page.py` 里** —— 2026-10-06 搬的：原来**只读 `trace.html` 一个文件**，而**那正是它当初没拦住 `approvals.html` 的原因**；现在**扫 `api/static/` 下每一个 `.html`**（实测 **6 个**）。📄 `DEC-094` §三·A。<br>📌 **判据（可打印）**：`grep -n "getJSON('/\|fetch('/" api/static/web/approvals.html` ⇒ **4 条**（在 `loadPending` / `openContext` / `decide` / `loadHistory` 四处），**现已全部带 `/api/v1`**（✅ 2026-10-06 修，`DEC-094`）。⚠️ **⛔ 别抄行号**（这次修复本身就把它们下移了 5 行）。 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/token_tracker.md` | **配额**那一层的数据源（`get_token_budget_info`）—— 本文件只负责在中间件里消费它 |
| `docs/specs/归档/quota_limiter.md` | ⚰️ **已归档** —— 原先的「每日**次数**」计数器，**2026-10-03 随 `DEC-046` 删除** |
| `后端补齐清单` **B9-b** | 限流分桶加验签（**2026-09-30 已做**） |
| `后端补齐清单` **B12** | 错误文案 + `retry_after`（⚠️ **本文把落点从 1 处更正为 4 处**） |
| `api/test_rate_limit_identity.py` | `resolve_rate_limit_identity` 的 **8 条**回归测试（⚠️ 2026-10-05 批 3 **一条都没改** —— `None` 与 `"anonymous"` 没有互相污染） |
| 🆕 `api/test_auth_db_unavailable.py` | **批 3（`N9`）· 22 条** —— 其中**第三组**直接调两个中间件的 `dispatch`（⚠️ **只测函数不够**：删掉"照 `None` 办事"那两行，函数级用例照样全绿） |
| 🆕 `docs/decisions/DEC-079` | `N9` 的 **503** 口径 + 四层 fail-open/fail-closed 分工 |
| `api/test_public_paths.py` | `MIDDLEWARE_EXEMPT_PATHS` 与真实路由的一致性 |
| `api/test_route_auth_scan.py` | **改名与接线那一轮的判据**（`DEC-074`）—— 9 条：扫描口径必须**看得见 WS**、纯函数**不许 `chdir`**、**自证**旧口径扫不到 WS |
| `scripts/check_route_auth.py` | ⭐ **「哪些路由没鉴权」的权威判据** —— ⛔ **别读名单、读它**（现含 WS） |
| `DEC-074` | 改名 + **把上面那个脚本真的接进 CI 与提交门**（此前它**哪都没跑**） |
| 🔴 `docs/decisions/DEC-088-接管页与硬门D的三个缺口.md` | **第二条页面路由 `/approvals` 的依据**（§3.3 —— 硬门 D 的反例原文是「界面上找不到」，所以那一栏**只能靠页面**）· 消费它的接口在 `docs/specs/api_v1_agent.md` |
| 🆕 `docs/decisions/DEC-093-Trace页两轴分屏.md` | **第三条页面路由 `/trace` 的依据** —— ⭐ 同时是**「302 对 ≠ 页面能用」那个事故**（`approvals.html` 4 条 URL 少 `/api/v1`）的**首次记录处** |
| 🆕 `docs/decisions/DEC-094-前缀事故收尾与CI用例改glob.md` | **那个事故的收尾**（✅ 4 条 URL 已修 · 守卫从"盯一页"改成"盯全站"）· **`ci.yml` 的 `node --test` 改 glob** · 🔴 **裸 glob 的反证实测**（匹配不到 ⇒ `tests 0` / 退出码 0） |
| `api/test_trace_page.py` | **6 条** —— 前 3 条照抄 `/chat`/`/approvals`，**后 3 条是页面坏法的守卫**（见「看代码会误判」表末两行）。⚠️ **原第 4 条已搬去 `api/test_web_pages.py`** |
| 🆕 `api/test_web_pages.py` | **7 条** —— **扫 `api/static/` 下每一个 `.html`**（实测 **6 个**）里 `getJSON(...)`/`fetch(...)` 的字面量必须以 `/api/v1` 开头 + **1 条防空跑**（`test_page_scan_is_not_vacuous`）。⚠️ **⛔ 别改回逐页列名** |
| `docs/specs/static_frontend.md` | **那三条页面路由指向的地方**（页面本体 / 纯逻辑 / 用例） |
