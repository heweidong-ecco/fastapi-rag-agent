# `app/routing/api_v1.py`

| 项 | 内容 |
|---|---|
| **状态** | ✅ **2026-10-04（`DEC-065`）鉴权与端点双收口** —— **9 条路由**里 **6 条带 `Depends(require_admin)`**，其余 3 条（`/` · `/auth/login` · `/auth/refresh`）是**有意公开**的 ⇒ **匿名可调的 = 0 条**（**唯一例外是本 spec 管不到的 `/api/v1/`，那是 `main.py` 的根路径**）。<br>🔴 **此前是**：「11 条路由里【只有 1 条】带鉴权依赖」—— 见下方 ⚠️①②③④ 四行，**四行都已随本次收口**（保留原文供查）<br>🔴 **2026-10-04（`DEC-065`）另删 2 条**：`/users/{user_id}`（**不查库**）· `/tool/benchmark`（**benchmark 的是 mock**）⇒ **11 → 9**<br>⚠️ **本 spec 曾推翻先前对 `B9` 的一个判断**（见 ⚠️②）<br>🔴 **2026-10-03（`①b` Task 6 · `DEC-046`）**：`/debug/quota` 的返回从「每日**次数**」换成「每日 **token**」—— **字段名没变、单位变了** |
| **对外提供** | **9 条路由**：`/` · `/auth/login` · `/auth/refresh` · `/admin/create_user` · `/debug/count` · `/debug/quota/{user_name}` · `/debug/cache_stats` · `/debug/rate_limit/{user_name}` · `/rag/benchmark-embedding`<br>🔴 **计数沿革**：11 →（2026-10-04 · `DEC-065`）**9**（删 `/users/{user_id}` · `/tool/benchmark`）。<br>📌 **判据（可打印）**：`grep -c '^@router\.' app/routing/api_v1.py` ⇒ **9** · `grep -c '= Depends(require_admin)' app/routing/api_v1.py` ⇒ **6**（⚠️ **`= ` 不能省** —— 注释里也有这个串，不带会数成 10） |
| **谁在用** | `main.py` 挂载 · 前端（未做） |
| **规模** | 327 行 · ⚠️ **21 个 import 没被使用**（🔴 那是 **2026-10-03 之前**的实测；本文件当天改过 `import`，🔴 **2026-10-04 `DEC-065` 又动了 2 行**，⬜ **数字待重核**) |

## ✅ 做了什么

- **认证两条**：`/auth/login`（`:70`，`authenticate_user` → 双令牌）· `/auth/refresh`（`:90`）
- **用户管理**：`/admin/create_user`（`:137`，**6 条带 `Depends(require_admin)` 的路由之一**）
- **一堆 `/debug/*`**（4 条）：`/debug/count`（`:203` 直查 `documents` 行数）· `/debug/quota/{user_name}`（`:216`）·
  `/debug/cache_stats`（`:274` 扫 `emb:*`）· `/debug/rate_limit/{user_name}`（`:312`）
- **对比测试**（原 **2** 条，现 **1** 条）：`/rag/benchmark-embedding`（`:240`，**真调 embedding 两次**）·
  ~~`/tool/benchmark`~~ 🔴 **2026-10-04 删**（`DEC-065`）—— 它 benchmark 的是 **mock**
  （`get_weather` = `time.sleep(2)` + 硬编码串）⇒ **证明不了生产事实**。
- ~~`/users/{user_id}`~~ 🔴 **2026-10-04 删**（`DEC-065`）：**一行数据都不读**（见 ⚠️④）。

> 📌 **上面的行号是 2026-10-04 用 `grep -n '^    "/' app/routing/api_v1.py` 现取的**（路由装饰器里那一行）。
> ⚠️ **沿革**：2026-10-03 取过一轮（当时本文件新增 16 行 ⇒ 更早的行号整体位移）；
> **2026-10-04 `DEC-065` 又改动本文件**（删 2 条端点 ≈ −30 行、5 条加鉴权 +5 行、2 行 import 注释 +5 行）
> ⇒ **上面这一组是重取的**。⛔ 别照 2026-10-03 那组读。
> 🔴 **只重取了本文件（`api_v1.py`）的**；⚠️ **全仓 spec 的 `:NNN` 系统性漂移仍是待办 `N8`**（⬜ 未处理）。

## 🟡 做到哪 / 缺什么

- ✅ ~~🔴 **鉴权缺失**（见 ⚠️①）~~ **2026-10-04 已收口**（`DEC-065`）：**6 条带 `require_admin`**，
  其余 3 条**有意公开** ⇒ **匿名可调 0 条**。⚠️ 追溯口径见 ⚠️①②③（**三行的"现状"已不成立，原文保留**）。
- ⬜ **仍未裁**：`/debug/*` 这类**调试端点到底要不要挂到线上**（**现在已锁定为仅管理员可用**，
  但"锁住"与"线上不挂载"是两件事 —— `app/routing/specs/api_v1.md` 这一条**仍然开着**）。
- 🔴 **21 个未使用 import**（实测）：`insert_document` · `insert_batch_documents` · `client` · `calculator` ·
  `rerank_search` · `hybrid_search_with_rewrite` · `create_fast_pipeline` · `create_accurate_pipeline` ·
  `create_full_pipeline` · `DocumentPreprocessor` · `split_text_with_filter` · `parse_document` ·
  `get_chat_history` · `append_chat_history` · **`agent_graph`** · `File` · `UploadFile` ·
  `JSONResponse` · `StreamingResponse` …（`api_v1.py:12-51`）
  <br>⚠️ 原列里还有 **`UserRole`** —— **2026-10-03 已随 `DEC-046` 从 `import` 行移除**（本文件从未用它）⇒ **那个名字不再属于这份清单**。
  ⇒ ⚠️ 本仓 `docs/说明/测试.md` 记的「**103 个未使用导入**」被**裁「先挂起」** ⇒ **本文件是其中一份**
- ✅ ~~⚠️ **`/users/{user_id}` 根本不查库**（见 ⚠️④）~~ **2026-10-04 直接删了**（`DEC-065`）。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **① 「这是主路由，鉴权有中间件兜着」** | ✅ **2026-10-04（`DEC-065`）已收口**：**9 条路由里 6 条带 `Depends(require_admin)`**，其余 3 条（`/` · `/auth/login` · `/auth/refresh`）**有意公开** ⇒ **匿名可调 0 条**。<br>📌 **判据（可打印）**：`grep -c '= Depends(require_admin)' app/routing/api_v1.py` ⇒ **6**。<br>⚠️ **⚠️ 那个 `= ` 不能省** —— 写成 `grep -c 'Depends(require_admin)'` 会数到 **10**：**墓碑注释与文档字符串里也有这个串**（本仓判据纪律第 2 条：**⛔ 别只数"有几处"**）。<br>⚠️ **原文（收口前，保留供查）**：⛔ **中间件只做限流与配额，⛔ 不做鉴权** —— 鉴权靠**路由自己的 `Depends(...)`**。<br>**而本文件 11 条路由里，只有 `create_user`（`:159`）有**（`grep -n "Depends(" app/routing/api_v1.py` **实测：只有那一条**）。<br>⇒ 其余 10 条**任何人（含匿名）可调**。只有 `/auth/login` · `/auth/refresh` 是**有意公开**的。 |
| 🔴 **② 「匿名只能打到不烧钱的端点」** | ✅ **2026-10-04（`DEC-065`）已不成立** —— 该端点**已带 `Depends(require_admin)`**，匿名打 ⇒ **401**（**实测**，见下）。<br>⚠️ **⚠️ 是 401 ⛔ 不是 403** —— **没带凭据** ⇒ `AUTH_MISSING`（**401**）；**带上非管理员的凭据**才轮到 `FORBIDDEN`（**403**，`app/core/exceptions.py` 的映射表）。<br>**实测（2026-10-04 · 裸 `TestClient`，5 条新收口路由一条不落）**：<br>`POST /api/v1/rag/benchmark-embedding {"question":"x"}` + `GET /api/v1/debug/{count,cache_stats,quota/admin,rate_limit/admin}` ⇒ **全部 401**，体为 `{"error":"请提供 API Key 或 Bearer Token","code":"AUTH_MISSING","status_code":401}`。<br>⚠️ **原文（收口前，保留供查）**：⛔ **错。`/api/v1/rag/benchmark-embedding` 匿名可打，且【真花钱】。**<br>**实测（2026-09-30，服务运行中）**：<br>```bash<br>curl -X POST http://127.0.0.1:8000/api/v1/rag/benchmark-embedding \\<br>  -H "Content-Type: application/json" -d '{"question":"匿名能烧钱吗"}'<br># → HTTP 200<br># → {"first_call_ms": 385.71, "second_call_ms": 1.12, ...}<br>```<br>**不带 `X-API-Key`、不带 `Authorization`** ⇒ **200**，且 **385ms = 真调了 DashScope**（第二次 1.12ms 是缓存命中）。<br>⚠️ **配额对匿名是跳过的**（`app/main.py:314` 的 `if not user_name:` ⇒ 直接放行）⇒ **匿名按 3 次/秒的速率无限烧 embedding**。<br>🔴 **它推翻了先前对 `B9` 的判断**（原写「匿名能打到的只有两个端点，而它们是桩」）—— **那个核法漏了一整类**：<br>只查了**标注"无需 API Key"的两个**，**没查"完全没有鉴权依赖"的**。⛔ 后者用 `grep Depends(` **一条命令就能列全**。 |
| 🔴 **③ 「`/debug/*` 只是调试，无所谓」** | ✅ **2026-10-04（`DEC-065`）：4 条 `/debug/*` 全部补上 `Depends(require_admin)`**。<br>⚠️ **收口后仍收【任意 `user_name`】参数** —— 那对**管理员是对的**（他就是要能查别人）；⛔ **但别把它当"用户自助查询"**。<br>⚠️ **原文（收口前，保留供查）**：⛔ **两条会泄露【任意用户名】的信息**：<br>· `/debug/quota/{user_name}`（`:215`）⇒ 返回该用户的 **role / `daily_limit` / `remaining` / `used_today`**<br>· `/debug/rate_limit/{user_name}`（`:314`）⇒ 返回该用户的**剩余令牌 + 容量 + 速率**<br>⚠️ 配合 `permission.get_user_role` 的**按名字硬编码**（`admin` / `test_user` 特判）⇒ **可用来【枚举用户名】**。<br>另有 `/debug/count`（文档总数）· `/debug/cache_stats`（缓存键样本）。<br>🔴 **2026-10-03 起**：`/debug/quota` 的数字**单位是 token**（字段名 `daily_limit` / `remaining` 保留）—— ⛔ **别当次数读**。 |
| ⚠️ **④ 「`/users/{user_id}` 会查用户」** | 🔴 **2026-10-04 该端点已【删除】**（`DEC-065`）—— ⛔ **不是修好了，是删了**。<br>⛔ **守卫**：`app/tests/test_removed_endpoints.py::test_users_by_id_stays_removed`（判据 = **404**）。<br>⚠️ **原文（保留供查）**：⛔ **不会** —— 它**直接回显参数**：`return {"user_id": user_id, "detail": include_detail}`（`:196`）。<br>**不查库、不看 `user_name`**。⇒ 它是**参数校验的演示**，不是用户查询。<br>📌 本 spec 早在 2026-09 就把它标成「**要么真查库，要么删**」（见下方"没裁"表第 **4** 条）⇒ 本次走的是**删**。 |
| ⚠️ **⑤ 「没用的 import 只是脏，没影响」** | ⚠️ **有一条不是** —— **`from agent_graph import agent_graph`（`:49`）** 会在 **import 期就构建那张图**（`agent_graph.py` 末尾 `agent_graph = build_agent_graph()`）。<br>⇒ 改 `agent_graph.py` 会**牵动 `api_v1.py` 的导入**，而本文件**根本不用它**。<br>📌 同族：`embedding_client.client` 也曾是模块级客户端（`ROADMAP` 待办 **T1**）—— ✅ **2026-10-05（批 6 · `DEC-082`）已了结**：本文件 `:35` 那行 `from embedding_client import client` **已删**（全仓唯一引用、且从未被使用），客户端改**惰性构造**。 |

## 关联

| 文档 | 说明 |
|---|---|
| `app/specs/main.md` | **中间件的 `PUBLIC_PATHS` 只豁免中间件，≠ 该端点不需要鉴权** —— 本文件的 ⚠️① 就是这条的实例 |
| `app/access/specs/rate_limiter.md` | `/debug/rate_limit` 用的是它；`user_name` 在那里是**桶名** |
| `app/specs/归档/quota_limiter.md` | ⚰️ **已归档** —— `/debug/quota` **原先**用的是它；**2026-10-03 起改用 `token_tracker.get_token_budget_info`**（`DEC-046`） |
| `后端补齐清单` **B9** | ⚠️ **本文件 ⚠️② 直接改变 B9 的状态** —— 见下 |
| `DEC-046` · `app/billing/specs/token_tracker.md` | 🔴 **2026-10-03 配额口径改动** —— `/debug/quota` 的数字**从「次数」变成 token**；`get_user_quota` **已删**（原是本文件 + `main.py` 共三个调用点之一） |
| `docs/说明/测试.md` §六 | 「103 个未使用导入」的一个来源（已裁「先挂起」） |

> ### 🔴 本 spec 对 `B9` 的影响（**重要 · 未收敛**）
>
> `B9` 的两条**挂起触发条件**是我 2026-09-30 写的：
>
> | | 触发条件 | 现在的状态 |
> |---|---|---|
> | ① 匿名按 IP 分桶 | 阶段⑦（上 Cloudflare）之后 | ⏸ 仍挂着（**条件未到**） |
> | ② **配额对匿名生效** | **一旦出现「匿名可打【且烧钱】的端点」** | ⚠️ **2026-10-04 已由另一条路消解** —— 该端点**匿名打不了了**（加鉴权 · `DEC-065` · 见 ⚠️②）⇒ **触发条件不再成立**。 |
>
> ⇒ 🔴 **2026-10-04（`DEC-065`）后，`B9-②` 的触发条件【已消失】**（原来的问题端点被锁上了，
>    **不是**"配额对匿名生效"了 —— ⚠️ **这两条路别混**）。⇒ **`B9-②` 可以正式摘掉**。
> ⚠️ **但 `B9-①`（匿名按 IP 分桶）仍然挂着**，条件未到。

> ### ✅ 要不要做 —— **2026-10-04（`DEC-065`）已全部闭合**
>
> | # | 事 | 结果 |
> |---|---|---|
> | **1** | 🔴 **给 `/debug/*` 加鉴权**（至少 `require_admin`），或**决定线上不挂载它们** | ✅ **已加 `require_admin`**（4 条）。<br>⬜ **但"线上要不要挂载"仍未裁** —— 见下方「仍未裁」。 |
> | **2** | 🔴 **`/rag/benchmark-embedding` 加鉴权** | ✅ **已加 `require_admin`**（`DEC-065`）。 |
> | **3** | ⚠️ **21 个未使用 import** | ⏸ **仍挂起**（`T6`）⇒ ⛔ **别顺手清**（本次只动了**因删端点而失效的那 2 行**）。 |
> | **4** | ⚠️ **`/users/{user_id}` 要么真查库，要么删** | ✅ **走了「删」**（`DEC-065`）。 |
>
> #### ⬜ 仍未裁（本次**没动**）
>
> - ⚠️ **`/debug/*` 这类调试端点到底要不要挂到线上** —— **现在已锁成"仅管理员"**，
>   但「**锁住**」与「**线上不挂载**」是**两件事**。**这一条仍然开着。**
> - ⚠️ **`/api/v1/`（`main.py` 的根路径）仍无鉴权** —— 它是**唯一**一条剩下的
>   （`scripts/route-auth-baseline.txt` 现为 **1 条**）。**是否有意公开，本 spec 未裁。**
