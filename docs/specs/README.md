# `docs/specs/` —— 模块规格

> ## 这份目录回答什么
>
> ### **「有什么、没有什么、还缺什么模块？」**
>
> 本仓原先只有 `ROADMAP` 的**功能现状表**（按**功能**排：RAG检索 / 流式 / 认证 / 限额…），
> 但**没有任何地方能回答"这个模块做到哪了"** —— **要读代码才知道**。
> ⇒ **本目录补的就是这个。**
>
> ---
>
> ## 和别处的分工（**别读成重复**）
>
> | 想知道 | 去哪 | 视角 |
> |---|---|---|
> | **有哪些功能、什么状态** | `ROADMAP.md` 的功能现状表 | **按功能** |
> | **模块之间怎么连**（请求流 / 依赖） | `docs/原理/架构.md` | **架构视角** |
> | ⭐ **这个模块做到哪、看代码会误判什么** | **本目录**（一个模块一份） | **模块视角** |
> | 接口 / 环境变量 / 表结构 | `docs/契约/` | 契约视角 |

---

## 📋 模块对账表

<!-- MODULE-TABLE-BEGIN -->
<!-- 本表由 `bash scripts/spec_status.sh --write` 生成 —— ⛔ 别手改 -->

| 模块 | 行数 | spec | 自报状态 |
|---|---:|---|---|
| `api/agent_checkpointer.py` | 120 | ✅ [`specs/agent_checkpointer.md`](./agent_checkpointer.md) | 🟡 **地基在，但零测试 · 且有一处忽略配置** |
| `api/agent_graph.py` | 151 | ✅ [`specs/agent_graph.md`](./agent_graph.md) | ⚰️ **遗留 / 未经裁决** —— **6 套 Agent 实现之一** |
| `api/agent_graph_advanced.py` | 400 | ✅ [`specs/agent_graph_advanced.md`](./agent_graph_advanced.md) | 🟡 **可用，且是生产链** —— 但 🔴 **有两处实锤缺陷**（见下）<br>🔵 **改造中**：`B7` 要动它的 `llm`（`:39`，现在**没有 `max_tokens`**） |
| `api/agent_graph_advanced_learning.py` | 397 | 🔴 **缺** | ❓ 未知 |
| `api/answer_with_citations.py` | 58 | ✅ [`specs/answer_with_citations.md`](./answer_with_citations.md) | 🟡 **后端可用 · 但【默认不启用】—— 且零测试** |
| `api/api_v1.py` | 313 | ✅ [`specs/api_v1.md`](./api_v1.md) | 🔴 **可用，但 11 条路由里【只有 1 条】带鉴权依赖** —— 其余任何人可调（含会花钱的和会泄露信息的）<br>⚠️ **本 spec 推翻了先前对 `B9` 的一个判断**（见 ⚠️②） |
| `api/api_v1_agent.py` | 744 | ✅ [`specs/api_v1_agent.md`](./api_v1_agent.md) | 🟡 **可用，但 28 个路由【全都非流式】** —— `StreamingResponse` / `text/event-stream` / `yield` **全为 0**<br>🔵 **改造中**：本文件下方有 **实施计划 ②**（人工接管）与 **③**（流式与取消） |
| `api/api_v1_rag.py` | 900 | ✅ [`specs/api_v1_rag.md`](./api_v1_rag.md) | 🟡 **部分可用** —— 有 3 条是"模拟类测试" |
| `api/auth.py` | 108 | 🔴 **缺** | ❓ 未知 |
| `api/bm25_index.py` | 66 | 🔴 **缺** | ❓ 未知 |
| `api/browser_tools.py` | 84 | 🔴 **缺** | ❓ 未知 |
| `api/cache.py` | 76 | 🔴 **缺** | ❓ 未知 |
| `api/chunker.py` | 65 | 🔴 **缺** | ❓ 未知 |
| `api/code_executor.py` | 70 | 🔴 **缺** | ❓ 未知 |
| `api/code_executor_impl.py` | 218 | 🔴 **缺** | ❓ 未知 |
| `api/config.py` | 83 | 🔴 **缺** | ❓ 未知 |
| `api/cost_dashboard.py` | 270 | 🔴 **缺** | ❓ 未知 |
| `api/db.py` | 245 | 🔴 **缺** | ❓ 未知 |
| `api/db_metadata.py` | 84 | 🔴 **缺** | ❓ 未知 |
| `api/deps.py` | 78 | 🔴 **缺** | ❓ 未知 |
| `api/document_parser.py` | 242 | 🔴 **缺** | ❓ 未知 |
| `api/document_preprocessor.py` | 221 | 🔴 **缺** | ❓ 未知 |
| `api/embedding_client.py` | 48 | ✅ [`specs/embedding_client.md`](./embedding_client.md) | 🟡 **可用，但有一处【启动崩溃】隐患**（`ROADMAP` 待办 **T1**） |
| `api/evaluate_with_ragas.py` | 296 | 🔴 **缺** | ❓ 未知 |
| `api/exceptions.py` | 66 | 🔴 **缺** | ❓ 未知 |
| `api/hybrid_search.py` | 139 | ✅ [`specs/hybrid_search.md`](./hybrid_search.md) | 🟡 **可用，但它在全仓是【第二份 RRF 实现】** |
| `api/jwt_handler.py` | 74 | 🔴 **缺** | ❓ 未知 |
| `api/logger_config.py` | 46 | 🔴 **缺** | ❓ 未知 |
| `api/main.py` | 586 | ✅ [`specs/main.md`](./main.md) | 🟡 **可用** —— 应用装配 + **3 条中间件** + 全局异常处理 + 看板挂载<br>🔴 **但有 4 处错误文案不准确**（见下）· 2026-09-30 起**限流分桶会验签了**（修 `B9-b`） |
| `api/mcp_server.py` | 112 | 🔴 **缺** | ❓ 未知 |
| `api/mcp_tool_factory.py` | 108 | 🔴 **缺** | ❓ 未知 |
| `api/memory_store.py` | 72 | 🔴 **缺** | ❓ 未知 |
| `api/metrics.py` | 36 | 🔴 **缺** | ❓ 未知 |
| `api/permission.py` | 35 | 🔴 **缺** | ❓ 未知 |
| `api/plan_execute.py` | 593 | ✅ [`specs/plan_execute.md`](./plan_execute.md) | 🟡 **可用** —— 规划 + 逐步**真调用工具**；有超时、有总预算、有重规划、有降级<br>🔴 **但查出 1 处真缺陷 + 5 处"看代码会误判"**（见下） |
| `api/query_rewriter.py` | 159 | 🔴 **缺** | ❓ 未知 |
| `api/quota_limiter.py` | 81 | ✅ [`specs/quota_limiter.md`](./quota_limiter.md) | 🟡 **可用，但匿名请求完全绕过它** |
| `api/rag_pipeline.py` | 247 | 🔴 **缺** | ❓ 未知 |
| `api/rate_limiter.py` | 132 | ✅ [`specs/rate_limiter.md`](./rate_limiter.md) | 🟡 **可用** —— 基于 Redis 的令牌桶，**全局 + 用户两层**<br>🔴 **但它有 3 个"看代码看不出来"的性质**（见下 ⚠️ 节）—— 其中 2 条是本 spec 新查出来的 |
| `api/reranker.py` | 59 | ✅ [`specs/reranker.md`](./reranker.md) | 🟡 **仅开发机可用** |
| `api/schemas.py` | 104 | 🔴 **缺** | ❓ 未知 |
| `api/search_tools.py` | 129 | 🔴 **缺** | ❓ 未知 |
| `api/simple_tools.py` | 36 | 🔴 **缺** | ❓ 未知 |
| `api/simple_tools_impl.py` | 30 | 🔴 **缺** | ❓ 未知 |
| `api/token_tracker.py` | 744 | ✅ [`specs/token_tracker.md`](./token_tracker.md) | 🟡 **可用，但它是【三套额度口径】的其中一套** —— 见下 ⚠️<br>🔵 **改造中**：本文件下方有 **实施计划 ①a**（把散在 4 个文件的额度常量收口） |
| `api/tool_cache.py` | 96 | 🔴 **缺** | ❓ 未知 |
| `api/tool_health.py` | 105 | 🔴 **缺** | ❓ 未知 |
| `api/tool_visualizer.py` | 129 | 🔴 **缺** | ❓ 未知 |
| `api/tools_with_cache.py` | 17 | 🔴 **缺** | ❓ 未知 |
| `api/websocket_callback.py` | 52 | 🔴 **缺** | ❓ 未知 |
<!-- MODULE-TABLE-END -->

> ⛔ **这张表【不要手改】** —— 它是 `scripts/spec_status.sh --write` 生成的。
> 理由同 `list_endpoints.sh`：**手写的清单必然过期**。
>
> 📌 **`spec` 列写「🔴 缺」的，就是"还没人核过这个模块做到哪"** —— **那本身就是信息。**

---

## 怎么写一份 spec

**一个模块一份**，文件名 = 模块名（`api/reranker.py` ⇒ `docs/specs/reranker.md`）。

```markdown
# `api/<模块>.py`

| 项 | 内容 |
|---|---|
| **状态** | ✅ 完整 / 🟡 部分可用 / ⬜ 未做 / ⚰️ 遗留（看代码会以为是产品功能） |
| **对外提供** | 函数 / 类 / 端点 |
| **谁在用** | |

## ✅ 做了什么
## 🟡 做到哪 / 缺什么
## ⚠️ 看代码会误判的地方        ← ⭐ **这一节是整份 spec 的价值所在**
## 关联
```

> ### ⭐ 为什么第三节最重要
>
> **前两节读代码也能推出来** —— 只有第三节**读代码推不出来**。
>
> 真实例子：
> ```
> api/reranker.py     文件在、代码完整 ⇒ 看着像"做完了"
>                     实际：镜像里没装 torch ⇒ 【容器里跑不了】
>
> api/agent_graph.py  4 套 Agent 实现之一 ⇒ 看着像"产品功能"
>                     实际：哪套是产品版本【未裁】(M5)
>
> api/api_v1_rag.py   15 条端点 ⇒ 看着像个正经模块
>                     实际：里面 3 条是"模拟类测试"（返回假数据）
> ```

---

## 状态图例

| 图例 | 意思 |
|---|---|
| ✅ **完整** | 功能完整、可用、**且验证过** |
| 🟡 **部分可用** | 能跑但有明确限制（写在 §🟡） |
| ⬜ **未做** | 代码骨架在，功能没实现 |
| ⚰️ **遗留** | 已被取代 / 不打算维护，**但还在线上**（看代码会误判） |
| ❓ **未知** | **还没人核过** —— 不是"没问题" |

---

## 🔧 怎么维护（**三条**）

| # | 什么时候 | 做什么 |
|---|---|---|
| 1 | **做完一个模块的功能** | ⭐ **更新它的 spec**（`CLAUDE.md` 的规矩） |
| 2 | **新增一个模块** | ⭐ **必须同时建 spec** —— **`pre-commit-gates.py` 会【硬拦】** |
| 3 | 想起来的时候 | 跑 `bash scripts/spec_status.sh` 看**还缺哪些** |

```bash
bash scripts/spec_status.sh            # 对账：谁有 spec、谁没有
bash scripts/spec_status.sh --write    # 顺带重写上面那张模块表
bash scripts/spec_status.sh --missing  # 只列缺的
```

📌 **也可以打 `/specs`**（斜杠命令，见 `.claude/commands/`）。

---

## ⚠️ 一条已知的局限（**别指望它 100% 准时**）

**spec 是人/agent 写的 ⇒ 它会过期。** hook 只能**拦住"新增模块没 spec"**（能机械判），
**"改了已有模块要不要更新 spec"是判断，机械判不了** ⇒ 只能**提醒**。

⇒ **所以第 3 条（跑对账）才是最终兜底。**
📌 本仓对这类事有明文教训：「**门挂在别处，就等于没有门**」——
**8 个 PR 一次都没跑过 `/留痕-checks`**。**⇒ 对账能查出来，就不算失控。**

---

## ⚙️ 本目录的自动机制（**2026-09-29 建**）

| 机制 | 在哪 | 拦不拦 |
|---|---|---|
| **提交前第 ④ 道门** | `.claude/hooks/pre-commit-gates.py` | ✅ **硬拦**：**新增了 `api/X.py` 但 `docs/specs/` 下与模块同名的那个文件 不存在** |
| **写完 `api/*.py` 后提醒** | `.claude/hooks/spec-remind.py` | ⛔ 不拦（写代码过程中太频繁） |
| **`/specs` 命令** | `.claude/commands/specs.md` | 手动跑对账 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/文档地图.md` | 全项目文档索引 |
| `docs/原理/架构.md` | 架构视角（模块怎么连） |
| `ROADMAP.md` | 功能视角（有哪些功能） |
| `scripts/spec_status.sh` | 对账脚本 |
