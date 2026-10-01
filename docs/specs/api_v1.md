# `api/api_v1.py`

| 项 | 内容 |
|---|---|
| **状态** | 🔴 **可用，但 11 条路由里【只有 1 条】带鉴权依赖** —— 其余任何人可调（含会花钱的和会泄露信息的）<br>⚠️ **本 spec 推翻了先前对 `B9` 的一个判断**（见 ⚠️②） |
| **对外提供** | 11 条路由：`/` · `/auth/login` · `/auth/refresh` · `/admin/create_user` · `/users/{user_id}` · `/debug/count` · `/debug/quota/{user_name}` · `/debug/cache_stats` · `/debug/rate_limit/{user_name}` · `/rag/benchmark-embedding` · `/tool/benchmark` |
| **谁在用** | `main.py` 挂载 · 前端（未做） |
| **规模** | 313 行 · ⚠️ **21 个 import 没被使用**（实测） |

## ✅ 做了什么

- **认证两条**：`/auth/login`（`:73`，`authenticate_user` → 双令牌）· `/auth/refresh`（`:119`）
- **用户管理**：`/admin/create_user`（`:155`，**唯一带 `Depends(require_admin)` 的路由**）
- **一堆 `/debug/*`**：`/debug/count`（`:204` 直查 `documents` 行数）· `/debug/quota/{user_name}`（`:218`）·
  `/debug/cache_stats`（`:259` 扫 `emb:*`）· `/debug/rate_limit/{user_name}`（`:302`）
- **两个"对比测试"**：`/rag/benchmark-embedding`（`:236`，**真调 embedding 两次**）· `/tool/benchmark`（`:277`，真调 `get_weather` 两次）

## 🟡 做到哪 / 缺什么

- 🔴 **鉴权缺失**（见 ⚠️①）
- 🔴 **21 个未使用 import**（实测）：`insert_document` · `insert_batch_documents` · `client` · `calculator` ·
  `rerank_search` · `hybrid_search_with_rewrite` · `create_fast_pipeline` · `create_accurate_pipeline` ·
  `create_full_pipeline` · `DocumentPreprocessor` · `split_text_with_filter` · `parse_document` ·
  `get_chat_history` · `append_chat_history` · **`agent_graph`** · `File` · `UploadFile` ·
  `JSONResponse` · `StreamingResponse` · `UserRole` …（`api_v1.py:12-51`）
  ⇒ ⚠️ 本仓 `docs/说明/测试.md` 记的「**103 个未使用导入**」被**裁「先挂起」** ⇒ **本文件是其中一份**
- ⚠️ **`/users/{user_id}` 根本不查库**（见 ⚠️④）
- ⚠️ `/debug/*` 这类**调试端点会不会保留到线上**，**未裁**

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **① 「这是主路由，鉴权有中间件兜着」** | ⛔ **中间件只做限流与配额，⛔ 不做鉴权** —— 鉴权靠**路由自己的 `Depends(...)`**。<br>**而本文件 11 条路由里，只有 `create_user`（`:157`）有**（`grep -n "Depends(" api_v1.py` **实测：只有那一条**）。<br>⇒ 其余 10 条**任何人（含匿名）可调**。只有 `/auth/login` · `/auth/refresh` 是**有意公开**的。 |
| 🔴 **② 「匿名只能打到不烧钱的端点」** | ⛔ **错。`/api/v1/rag/benchmark-embedding` 匿名可打，且【真花钱】。**<br>**实测（2026-09-30，服务运行中）**：<br>```bash<br>curl -X POST http://127.0.0.1:8000/api/v1/rag/benchmark-embedding \\<br>  -H "Content-Type: application/json" -d '{"question":"匿名能烧钱吗"}'<br># → HTTP 200<br># → {"first_call_ms": 385.71, "second_call_ms": 1.12, ...}<br>```<br>**不带 `X-API-Key`、不带 `Authorization`** ⇒ **200**，且 **385ms = 真调了 DashScope**（第二次 1.12ms 是缓存命中）。<br>⚠️ **配额对匿名是跳过的**（`main.py:222` 的 `if user_name:`）⇒ **匿名按 3 次/秒的速率无限烧 embedding**。<br>🔴 **它推翻了先前对 `B9` 的判断**（原写「匿名能打到的只有两个端点，而它们是桩」）—— **那个核法漏了一整类**：<br>只查了**标注"无需 API Key"的两个**，**没查"完全没有鉴权依赖"的**。⛔ 后者用 `grep Depends(` **一条命令就能列全**。 |
| 🔴 **③ 「`/debug/*` 只是调试，无所谓」** | ⛔ **两条会泄露【任意用户名】的信息**：<br>· `/debug/quota/{user_name}`（`:218`）⇒ 返回该用户的 **role / daily_limit / remaining**<br>· `/debug/rate_limit/{user_name}`（`:302`）⇒ 返回该用户的**剩余令牌 + 容量 + 速率**<br>⚠️ 配合 `permission.get_user_role` 的**按名字硬编码**（`admin` / `test_user` 特判）⇒ **可用来【枚举用户名】**。<br>另有 `/debug/count`（文档总数）· `/debug/cache_stats`（缓存键样本）。 |
| ⚠️ **④ 「`/users/{user_id}` 会查用户」** | ⛔ **不会** —— 它**直接回显参数**：`return {"user_id": user_id, "detail": include_detail}`（`:194`）。<br>**不查库、不看 `user_name`**。⇒ 它是**参数校验的演示**，不是用户查询。 |
| ⚠️ **⑤ 「没用的 import 只是脏，没影响」** | ⚠️ **有一条不是** —— **`from agent_graph import agent_graph`（`:49`）** 会在 **import 期就构建那张图**（`agent_graph.py` 末尾 `agent_graph = build_agent_graph()`）。<br>⇒ 改 `agent_graph.py` 会**牵动 `api_v1.py` 的导入**，而本文件**根本不用它**。<br>📌 同族：`embedding_client.client` 也是模块级客户端（`ROADMAP` 待办 **T1**）。 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/main.md` | **中间件的 `PUBLIC_PATHS` 只豁免中间件，≠ 该端点不需要鉴权** —— 本文件的 ⚠️① 就是这条的实例 |
| `docs/specs/rate_limiter.md` | `/debug/rate_limit` 用的是它；`user_name` 在那里是**桶名** |
| `docs/specs/quota_limiter.md` | `/debug/quota` 用的是它 |
| `后端补齐清单` **B9** | ⚠️ **本文件 ⚠️② 直接改变 B9 的状态** —— 见下 |
| `后端补齐清单` **决策一** | `/debug/quota`（`:221`）是 `get_user_quota` 的**三个调用点之一** |
| `docs/说明/测试.md` §六 | 「103 个未使用导入」的一个来源（已裁「先挂起」） |

> ### 🔴 本 spec 对 `B9` 的影响（**重要 · 未收敛**）
>
> `B9` 的两条**挂起触发条件**是我 2026-09-30 写的：
>
> | | 触发条件 | 现在的状态 |
> |---|---|---|
> | ① 匿名按 IP 分桶 | 阶段⑦（上 Cloudflare）之后 | ⏸ 仍挂着（**条件未到**） |
> | ② **配额对匿名生效** | **一旦出现「匿名可打【且烧钱】的端点」** | 🔴 **条件已满足** —— 见 ⚠️② |
>
> ⇒ **`B9-②` 不该继续挂着**：触发条件不是"将来会出现"，**是现在就存在**。
> ⚠️ 但我**没有去改 `后端补齐清单` / `待办总表`** —— 按你 2026-09-30 的指示，**收敛留到下一轮**。
> 📌 **这一条请带进下一轮。**

> ### ⬜ 要不要做（**没裁，写在这里免得丢**）
>
> | # | 事 | 为什么要紧 |
> |---|---|---|
> | **1** | 🔴 **给 `/debug/*` 加鉴权**（至少 `require_admin`），或**决定线上不挂载它们** | 现在**任何人**能查任意用户的角色/配额，还能烧 embedding |
> | **2** | 🔴 **`/rag/benchmark-embedding` 加鉴权** | **匿名烧钱**（实测证实） |
> | **3** | ⚠️ **21 个未使用 import** | ⚠️ 已被裁「**先挂起**」（`T6`）⇒ **本任务不新开**，⛔ 别顺手清 |
> | **4** | ⚠️ **`/users/{user_id}` 要么真查库，要么删** | 现在是个**回显参数的演示**，容易被当成真接口 |
