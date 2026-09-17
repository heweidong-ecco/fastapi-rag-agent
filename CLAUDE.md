# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

> ⚠️ **2026-09-17 起本文件改为【入库】**（业务方裁决）—— 此前在 `.gitignore:17`，现已移出。
> **它现在是 PUBLIC 仓库内容，不得写入明文凭据**（移出前已扫：5 个真实凭据 + 3 个历史泄露字面量，0 命中）。
> 最近一次全面复审：2026-08-17。重要修复记录见文末「本次复审修复记录」。

> ## 🔴 当前最高优先级（2026-09-15 业务方批准）：`docs/重构计划-2026-09-15.md`
>
> **开工前先读它。** 其余 M5 裁决工作**让位于它**。
>
> 它含一条**前提级更正**（与本文档下文若干处描述冲突，以它为准）：
>
> - 本机**能跑测试**（曾误判为"做不了运行期验证"）。但**不要借用** `ai-learning/venv` —— 它的 `fastapi 0.115.11` 与 `starlette 1.6.0` **不配对**，任何 `APIRouter(...)` 都建不起来
> - 正确做法：**在本仓自建隔离 venv** → `python3.10 -m venv venv && venv/bin/pip install -r api/requirements-test.txt`
> - `api/requirements-test.txt` 是 `requirements.txt` 的**剔重版**（只做减法）：去掉 `sentence-transformers`（拖 torch）等测试不需要的重依赖 —— 本仓 `api/reranker.py:14` 是真懒加载，**不需要 torch**
> - ⇒ **"切模块"不是测试的前置条件**
> - 执行顺序：**基线 → 修 bug → 归档 → 切模块 → M6**
>
> 另两处登记：`ROADMAP.md`「当前指针」最上方 · `docs/重构计划-2026-09-15.md` 正文

## ⚡ superpowers skills · 必用表（用户级 · 14 个）

> **用户指令（2026-09-17）**：「使用用户级中 superpowers 的 skills……**如果命中必须用**，
> 先写好，过程中我再动态调整。」
> **定位**：业务方 2026-09-17 裁决「**两份都留本仓**」—— 先在本仓试点，跑通再考虑提全局。
> **本表由体检定级**，依据见 `docs/skill-适配体检-2026-09-17.md`。

### ⛔ 第一条：**知道 skill 存在 ≠ 会用 skill**

每次会话我自动收到**所有 skill 的名字 + 一行描述**，但那**只是索引** ——
**只有调用 `Skill` 工具，正文才会进入上下文。没调用 = 这个 skill 等于不存在。**

> **实测佐证（本仓）**：此前 **8 个 PR 一次都没跑过 `/留痕-checks`**，而我每遍读 PR 纪律时
> 都"知道"它存在 —— 见 `docs/复盘/2026-09-16-八个PR跳过了留痕门.md`。**门挂在别处，就等于没有门。**

### A 级 · **命中必须用**（9 个 —— 与我们的工作流一致）

| 触发场景 | 必须用 | 原文判据 | 代价 |
|---|---|---|---|
| **任何 bug / 测试失败 / 异常行为**，提出修法之前 | `systematic-debugging` | before proposing fixes | ~10k |
| **实现任何功能或修 bug**，写实现代码之前 | `test-driven-development` | before writing implementation code | ~4k |
| **要说"做完了 / 修好了 / 过了"之前**，或提交 / 开 PR 之前 | `verification-before-completion` | **evidence before assertions always** | ~0.9k |
| 有 spec/需求要做多步任务，**动代码之前** | `writing-plans` | before touching code | ~2.2k |
| 已有书面计划要执行（带 review 检查点） | `executing-plans` | with review checkpoints | ~0.6k |
| 完成一个任务 / 大功能 / **合并之前** | `requesting-code-review` | | ~2.2k |
| **收到** code review 意见时（尤其看不懂或不认同的） | `receiving-code-review` | 要**技术较真与验证**，不是表演式认同、不是盲目照做 | ~1.6k |
| 实现完成、测试全过，要决定**怎么合入** | `finishing-a-development-branch` | | ~1.9k |
| **任何创造性工作之前**（加功能 / 建组件 / 改行为） | `brainstorming` | MUST use before any creative work | **~20k** ⚠️ |

> ⚠️ **`brainstorming` 是表里最贵的（≈20k tokens）** —— 它挂在"任何创造性工作之前"，
> 意味着**每个功能请求都会拉 20k**。本机上下文 1M，扛得住，但**要知道它是笔开销**。

### B 级 · `⬜ 待适配`（5 个 —— **它假设的工作流与我们不同**，用前先判）

| skill | 为什么待适配 | 我们的实际 |
|---|---|---|
| `using-git-worktrees` | 假设需要 worktree 隔离 | **在本仓直接干、一分支一 PR**；worktree 不是我们的模式 |
| `dispatching-parallel-agents` | 假设并行派发多 agent | **单人逐条确认** |
| `subagent-driven-development` | 假设用子 agent 执行计划 | 同上，且我们的规矩是「**改动等发话**」 |
| `writing-skills` | 假设常写 skill（且 **~26.8k**，表里最贵） | 极少写 |
| `using-superpowers` | ⚠️ **它的核心主张与本仓纪律冲突**（见下） | 只采纳它的「名字≠skill」，**不采纳"1% 就必须调用"** |

> ⚠️ **`using-superpowers` 的冲突点**（原文）：它要求「只要有 **1% 可能** skill 适用就**绝对必须**
> 调用」「**任何**回复或动作**之前**都要先调用 —— 包括提问、看代码、查文件」，还把
> 「这只是个小问题」「我先看一眼文件」全标成 **rationalizing**。
> **这与本仓「非必要的不要做」「改动等发话」正面冲突。**
> ✅ **好在它自己第 63 行写了**：`User instructions (CLAUDE.md …) take precedence over skills`
> ⇒ **以 CLAUDE.md 为准**，那条"1% 就必须调用"**不采纳**。

### 冲突与例外 —— **必须说出来，不许静默跳过**

1. **同场景命中多个** → 按上表**从上到下**依次执行。
   （例："修 bug" = `systematic-debugging` → `test-driven-development` → `verification-before-completion`）
2. **skill 与项目 `CLAUDE.md` / `ROADMAP.md` 冲突** → **以项目规矩为准**，并**写明冲突点**。
3. **skill 的判据在本仓对不上**（引用路径本仓没有）→ ⛔ **不许含糊通过**。
   有替代判据 → 标 `⬜ 待适配` 并**写明替代判据**；**没有 → 标 `⛔ 无法执行`，不当作通过**。
   规则见 `docs/规则草稿-规则必须绑定路径.md`。

> ⚠️ **已知不适配（2026-09-17 实测）**：`留痕-checks` 的 check 7 引用
> `contracts/tools-mcp` · `总纲.md` · `eval/README.md` · `eval/阈值.md` —— 这些路径在本仓
> **全都不存在**（评估在**另一个仓库** `agent-eval-gate`；本仓 `ci.yml` 无 eval 门）。
> 执行时**必须说明判据是我映射的**，不能假装照跑。

## 项目概述

基于 FastAPI、PostgreSQL+pgvector 和 Redis 构建的生产级 RAG（检索增强生成）+ Agent API 服务。使用阿里云百炼 DashScope 提供 Embedding（`text-embedding-v2`）和 LLM（`qwen-turbo`、`qwen-plus`），本地加载 BGE-Reranker-v2-m3 Cross-Encoder 模型进行重排序。

## 常用命令

```bash
# 完整生产环境启动（API + Postgres + Redis + Prometheus + Grafana）
docker compose up -d

# 本地开发：DB/Redis 用 Docker 启动，API 本地热重载运行
bash dev.sh
# 或手动执行：
cd api && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 运行全部测试（需要依赖已安装 + Postgres/Redis 已启动）
cd api && pytest -v

# 运行单个测试文件
cd api && pytest test_auth.py -v

# 数据库迁移（在 api/ 目录下执行，注意 env.py 会用 config 里的连接串覆盖 alembic.ini）
cd api && alembic upgrade head
cd api && alembic revision --autogenerate -m "描述信息"

# 性能压测
locust -f locustfile_hybrid.py
```

## 架构

### 入口与中间件链

`api/main.py` 创建 FastAPI 应用，并按以下顺序挂载中间件：

1. **HTTP 日志 + Prometheus 指标** — 每个请求生成唯一 `request_id`（ContextVar 实现，线程安全），记录 method/path/status/duration，通过 `metrics.py` 采集指标
2. **RateLimitMiddleware（限流）** — 两层令牌桶：全局（100次/秒，容量150）→ 用户级（3次/秒，容量20）。使用 Redis Lua 脚本保证原子性。跳过 `/`、`/docs`、`/openapi.json`、`/auth/login`、`/auth/refresh`、`/admin/create_user` 等公开路径
3. **QuotaMiddleware（配额）** — 按角色限制每日调用次数（免费用户：100次/天，付费用户：10000次/天，管理员：不限）。通过 X-API-Key 请求头或 Bearer JWT 识别用户身份
4. **TextNormalizationMiddleware（文本规范化）** — 自动将请求体中的全角字符转为半角，跳过 URL、Token 等非自然语言字段

> ⚠️ **中间件异常处理要点**：FastAPI 的 `@app.exception_handler(AppException)` 只捕获路由层抛出的异常。**在中间件 dispatch 中抛出的 `AppException` 不会被该处理器捕获**，会落到通用 `Exception` 处理器返回 500。因此中间件拒绝请求时必须直接返回 `JSONResponse`（限流/配额中间件均如此实现）。

### 路由结构

三个路由模块均挂载在 `/api/v1` 前缀下：

| 文件 | 职责 |
|------|------|
| `api/api_v1.py` | 公开接口（`/`）、认证（`/auth/login`、`/auth/refresh`）、管理员创建用户、调试接口（查看缓存状态、限流配额、Embedding 性能对比） |
| `api/api_v1_rag.py` | 文档管理（`/rag/insert`、`/rag/batch-insert`、`/rag/upload`）、检索（`/rag/pg_search`、`/rag/hybrid_search`）、流式生成（`/rag/stream`，SSE 实现带真中断）、带引用的答案生成、WebSocket Agent（`/ws/agent`、`/ws/test`）、文档清理规则 |
| `api/api_v1_agent.py` | LangGraph Agent 对话（`/agent/langgraph_chat`）、人工审批节点（`/agent/approve`）、多分支路由高级 Agent（`/agent/advanced_chat`）、Plan-Execute 模式、长期记忆（Mem0）、浏览器工具（Playwright）、Python 代码执行器、MCP Client 对话（`/agent/mcp_chat`）、MCP 工具列表、工具健康检查、Token 预算追踪与成本看板数据、执行轨迹可视化 |

### RAG 检索管线（`api/rag_pipeline.py`）

`RAGPipeline` 类支持三种检索模式，由可独立开关的环节组合而成：

- **fast（快速）**：仅向量检索（pgvector 余弦相似度）
- **accurate（精确）**：查询改写 → 混合检索（向量 + BM25）→ RRF 融合 → Cross-Encoder 重排序
- **full（完整）**：查询扩展 → 改写 → 混合检索 → RRF 融合 → 重排序 → LLM 生成答案

管线中的关键模块：
- `query_rewriter.py` — 基于 LLM 的查询扩展（生成多个变体）和上下文感知改写（指代消解、口语转书面语）。结果缓存在 Redis（1小时 TTL）
- `hybrid_search.py` — 使用 RRF（Reciprocal Rank Fusion，k=60）算法融合稠密向量检索和稀疏 BM25 关键词检索两路结果
- `reranker.py` — 懒加载 `BAAI/bge-reranker-v2-m3` CrossEncoder 模型，对候选文档进行精细排序
- `answer_with_citations.py` — 生成带 `[1]` 行内引用标记的 LLM 答案，支持溯源到原始文档块

### Agent 系统（LangGraph）

**三个 Agent 实现，注意区分：**

| 文件 | 路由接口 | 特点 |
|------|---------|------|
| `agent_graph.py` | `/agent/langgraph_chat` | 基础 Agent：LLM 决策节点 → 工具执行循环（DuckDuckGo 搜索、计算器、日期）。带人工审批节点（`interrupt_before=["approval"]`），配合 `/agent/approve` 接口 |
| `agent_graph_advanced.py` | `/agent/mcp_chat` | **MCP Client 版**高级 Agent：通过 MCP 协议动态调用工具（会话池管理，避免并发阻塞）、Mem0 长期记忆注入、多级 Token 预算检查（单次/单线程/每日）、工具调用缓存。全局实例 `mcp_agent` |
| `agent_graph_advanced_learning.py` | `/agent/advanced_chat` | **意图分类路由版**高级 Agent：supervisor 分类器（SEARCH/CALCULATOR/DATE/TRANSLATE/REACT）→ 专用子图（搜索部门/计算器部门/日期部门/翻译部门/ReAct 部门）。注意：此文件原名 `agent_graph_advanced_learning1.0.0.py`，含点号无法作为模块导入，已重命名 |

Agent 配套基础设施：
- `agent_checkpointer.py` — 基于 MemorySaver（默认）/ SqliteSaver（`AGENT_CHECKPOINT_BACKEND=sqlite`）的检查点持久化，保证对话连续性
- `plan_execute.py` — Plan-and-Execute 模式，适用于复杂多步任务（含动态重规划、质量检查）
- `memory_store.py` — Mem0 集成（本地 qdrant 模式），提供长期用户记忆
- `browser_tools.py` — 基于 Playwright 的网页抓取和截图
- `code_executor.py` — 沙箱化 Python 代码执行（白名单内置函数/模块 + 时间/输出限制）
- `mcp_server.py` / `mcp_tool_factory.py` — MCP（模型上下文协议）Server，用工厂函数自动从 `@tool` 函数注册工具定义与处理器
- `tool_health.py` — 通过 MCP 动态探测工具健康状态，自动降级
- `tool_visualizer.py` — 记录 Agent 工具调用轨迹（`/agent/trace/{thread_id}`）
- `token_tracker.py` — Token 用量/成本追踪、预算控制、月度报告（所有查询走数据库）

### 数据层

- **PostgreSQL + pgvector**：存储文档及其向量（1536维）。表结构在应用启动时通过 `db.py:create_table()` 自动创建。使用 psycopg2 `ThreadedConnectionPool` 连接池（默认最小2，最大30连接，`.env` 中 `DB_MIN_CONN`/`DB_MAX_CONN` 可调）
- **`get_db()` 上下文管理器**：始终从连接池获取连接，成功时 `commit()`，异常时 `rollback()`，最终 `putconn()` 归还。禁止直接创建原始连接（历史上曾出现重复定义 `get_db()` 覆盖连接池版本的 bug，已修复）
- **Redis**：承担三种职责 —（1）Embedding 缓存（MD5 键名，24小时 TTL，`emb:*` 前缀），（2）用户对话历史（24小时 TTL，保留最近5轮），（3）限流/配额计数器（Lua 脚本保证原子操作）
- **Alembic**：数据库迁移工具，配置在 `api/alembic/`。`env.py` 会用 `config.py` 中的连接串**覆盖** `alembic.ini` 里硬编码的 `sqlalchemy.url`，无需手动改 ini

### 认证与授权

双认证体系（`deps.py`）：
- **X-API-Key 请求头**：API Key 的 SHA256 哈希值存储在 `api_keys` 表中，含过期时间。通过 `auth.py:verify_api_key()` 验证
- **JWT Bearer Token**：短期令牌（access token，15分钟有效）+ 长期令牌（refresh token，7天有效）。使用 HS256 算法，密钥为 `JWT_SECRET_KEY`
- **混合认证**（`get_current_user_hybrid`）：优先尝试 API Key，无则回退到 JWT。注意 `HTTPBearer` 使用 `auto_error=False`——若为默认的 `True`，缺少 Authorization 头时会在依赖解析阶段直接抛 403，导致纯 API Key 认证全部失效
- **角色体系**（`permission.py`）：三级权限——`free`（免费，100次/天）、`premium`（付费，10000次/天）、`admin`（管理员，不限）。当前角色映射硬编码在 `get_user_role()` 中

### 配置管理

`api/config.py` 集中管理所有环境变量。敏感配置项（`DASHSCOPE_API_KEY`、`POSTGRES_PASSWORD`、`JWT_SECRET_KEY`）不设默认值——启动时 `validate_config()` 检测到缺失会拒绝启动。

**主机地址约定**：`.env` 中 `POSTGRES_HOST`/`REDIS_HOST` 填 **Docker 服务名**（`postgres`/`redis`）；本地开发时 `config.py` 会根据 `IS_DOCKER` 标志（`DOCKER_ENV` 环境变量）自动覆盖为 `localhost`。所有需要 Redis 连接的模块都应从 `config.py` 导入 `REDIS_HOST`/`REDIS_PORT`（不要直接用 `os.getenv` 读取，否则本地/Docker 切换会不一致）。

### 可观测性

- **日志**（`logger_config.py`）：Loguru 三通道输出——彩色控制台（DEBUG 级别）、按日滚动的文件日志（INFO 级别，保留30天）、错误日志单独存储（ERROR 级别，保留90天）。每条日志通过 `logger.bind(request_id=...)` 携带请求ID
- **指标**（`metrics.py`）：Prometheus 计数器/直方图/仪表盘，暴露在 `GET /metrics`
- **健康检查**：`/health`（检测数据库 + Redis 连通性）、`/ready`（Kubernetes 就绪探针，启动后10秒才开始响应就绪）
- **Token 追踪**（`token_tracker.py`）：按用户/用途/会话维度追踪 Token 用量和成本，持久化到数据库。预算消耗达 80% 时发出预警
- **成本看板**（`cost_dashboard.py`）：Gradio 可视化面板，挂载在 `/dashboard`

### 关键开发模式

- **错误处理**：所有业务错误统一使用 `AppException(ErrorCode, message)` 抛出。`ErrorCode` 枚举值与 HTTP 状态码的映射保存在 `ERROR_CODE_TO_HTTP_STATUS`。全局异常处理器同时捕获 `AppException` 和未处理的 `Exception`。⚠️ 中间件中不要抛 `AppException`（见上），直接返回 `JSONResponse`
- **数据库访问**：始终使用 `get_db()` 上下文管理器——自动从连接池获取连接，成功时提交，异常时回滚，最终归还连接。禁止直接创建原始连接
- **缓存策略**：Embedding 调用统一走 `embedding_client.get_embedding()`，内部先查 Redis 缓存再调 API。启动时 `warmup_cache()` 预热10个热点查询的 Embedding。查询改写结果同样在 Redis 中缓存
- **SSE 流式输出**：答案可通过 Server-Sent Events 流式返回，支持真中断（停止按钮会将已生成的部分内容保存为对话历史，避免 Token 浪费）
- **文档处理管道**：`document_preprocessor.py`（文本规范化）→ `document_parser.py`（解析 PDF/Word/Markdown/HTML）→ `chunker.py`（按文档类型选择分块策略）→ `embedding_client.py`（向量化）→ 入库
- **模型命名约定**：DashScope 模型名必须用 `qwen-turbo` / `qwen-plus` / `text-embedding-v2`。**不要使用 `qwen3.7-plus`**（DashScope 不存在该模型，调用会报错；历史代码中的误写已全部修正）

## 本次复审修复记录（2026-08-17）

以下为全面复审时发现并修复的问题，涉及**启动崩溃 / 运行崩溃 / 认证失效 / 数据丢失**：

1. **`api_v1_agent.py` 导入崩溃**：`from agent_graph_advanced import build_advanced_agent` 指向不存在的函数（该函数在 learning 文件中）。已将 `agent_graph_advanced_learning1.0.0.py` 重命名为 `agent_graph_advanced_learning.py`（原名含点号无法导入），并修正导入。同时清理了该文件内大量重复的 import 语句
2. **`agent_checkpointer.py` 空图编译**：`build_checkpointer_agent()` 只写了"添加节点和边的代码保持不变"注释，实际没加节点/边，编译空图在导入时报错。已补全 agent→tools→agent 的完整接线
3. **`token_tracker.py` NameError**：`record_usage()` 在构造 `TokenUsage` 时使用尚未赋值的 `cost`（`cost=cost`），每次调用必崩。已把成本计算移到构造之前
4. **`hybrid_search.py` 元组解包崩溃**：`reciprocal_rank_fusion` 按 3 元组解包 `(content, source, similarity)`，但 `db.search_similar` 实际返回 4 列 `(id, content, source, similarity)`，必抛 `ValueError`。已改为 4 元组并补 `id` 字段
5. **`tool_health.py` 启动崩溃**：在 async 的 `startup_event` 中调用 `asyncio.run()` 会抛 `RuntimeError`。已把 `update_tool_health`/`run_health_check` 改为 async，并同步更新 `main.py`、`api_v1_agent.py` 中的调用点为 `await`
6. **`deps.py` 认证失效**：`HTTPBearer()` 默认 `auto_error=True`，缺少 Authorization 头时纯 API Key 请求在依赖解析阶段被 403 拦截。已改为 `auto_error=False`，并为 `get_current_user_jwt` 补 None 分支
7. **`db.py` 数据丢失**：`get_db()` 被重复定义，后定义的简单连接版本覆盖了连接池版本，导致写入不提交（CLAUDE.md 描述的连接池/自动提交实际失效）。已删除重复定义，保留连接池版，并修正 `DB_CONFIG` 的硬编码 `user`
8. **错误模型名 `qwen3.7-plus`**：出现在 `agent_graph_advanced.py`、`agent_graph_advanced_learning.py`、`search_tools.py`、`api_v1_rag.py`（流式 + WebSocket）、`plan_execute.py`，全部改为 `qwen-plus`
9. **`agent_graph_advanced.py` 轨迹误报**：工具调用成功后仍记录"未找到工具"错误轨迹。已改为成功状态
10. **`api_v1_rag.py` SQL 参数颠倒**：`/rag/ask` 中 `WHERE requested_by = %s LIMIT %s` 传参为 `(req.top_k, user_name)`，LIMIT 收到用户名必报错。已交换为 `(user_name, req.top_k)`
11. **`api_v1_rag.py` WebSocket Agent 调用错误**：`create_tool_calling_agent` 的输入键应为 `input`、输出键为 `output`，原代码用 `messages` 导致 KeyError。已改为 `agent_executor.ainvoke({"input": ...})` 并读取 `result["output"]`
12. **`main.py` 限流返回 500**：中间件中 `raise AppException` 不会被 `@app.exception_handler(AppException)` 捕获，限流时返回 500 而非 429。已改为直接返回 429 `JSONResponse`；同时将 `/auth/login`、`/auth/refresh` 加入限流跳过名单（与配额中间件一致）
13. **`rag_pipeline.py` 失效过滤**：`SIMILARITY_THRESHOLD=0.7` 对 RRF 分数不成立（RRF 分数约 1/(k+rank)，k=60 时远小于 0.7），导致过滤逻辑形同虚设/误导。已改为仅重排序启用时按 `rerank_score >= 0` 过滤
14. **依赖缺失**：`requirements.txt` 缺少 `gradio`（`main.py` 挂载面板必需）、`sqlalchemy`（`db.py` 元数据定义必需）、`numpy`、`datasets`，已补充
15. **Redis 主机不一致**：`query_rewriter.py`、`agent_graph_advanced.py` 直接用 `os.getenv("REDIS_HOST", "redis")` 读取，本地开发会连错地址。已改为从 `config.py` 导入；`.env`/`.env.example` 的 `POSTGRES_HOST`/`REDIS_HOST` 统一改为 Docker 服务名
16. **`.gitignore` 补充**：新增 `.pytest_cache/`、`.mem0/`、`screenshots/`、`*.db`（运行期产物不入库）

### 实时环境测试补充修复（2026-08-17，在 venv + Docker 实机验证时发现）

17. **`code_executor.py` @tool docstring 位置错误**：`execute_python` 的 docstring 写在可执行代码之后（不再是 `__doc__`），langchain `@tool` 装饰器运行时报 `ValueError: Function must have a docstring`。已移到函数第一行
18. **`document_preprocessor.py` 正则损坏**：`remove_noise_markers` 中硬编码正则 `r'!\\[...'`（raw string 双重转义）导致 `re.error: unbalanced parenthesis`，文档上传（`process()`）必崩。已改为单层转义
19. **`memory_store.py` 适配 mem0>=2.0**：mem0 2.x 的 `Memory.__init__` 不再接受 dict 配置，改用 `Memory.from_config(dict)`
20. **`reranker.py` 真·懒加载**：原代码在模块顶层 `from sentence_transformers import CrossEncoder`，违背"懒加载"承诺，导致缺少该依赖时应用整体无法启动。已移入 `get_reranker()` 内部延迟导入
21. **限流/配额中间件豁免健康检查**：`/health`、`/ready`、`/metrics` 此前会被计入限流/配额，K8s/Docker 健康探针可能收到 429 被误判为不健康。已加入两个中间件的跳过名单
22. **限流按 JWT 用户分桶**：`RateLimitMiddleware` 之前只按 X-API-Key 分桶，JWT 用户全部挤在 `anonymous` 桶（3次/秒共享）。已支持从 Bearer Token 解析用户名，每用户独立桶
23. **`test_plan_constraints.py` 加 `@pytest.mark.skip`**：该文件是手动实验脚本（需必填参数），现标记 skip，`pytest` 套件干净通过
24. **`logger_config.py` 日志 KeyError**：日志格式引用 `{extra[request_id]}`，但未绑定 `request_id` 的日志（如启动日志）格式化时报 `KeyError`。已用 `logger.configure(extra={"request_id": "no-id"})` 提供默认值

### 已知遗留问题 / 环境注意

- **DashScope LLM 免费额度**：本机测试时 embedding API（`text-embedding-v2`）正常，但 **chat 模型（qwen-turbo/qwen-plus）免费额度已耗尽**，调用 LLM 的功能（答案生成、查询改写、Agent 对话）会返回 `403 Free quota exhausted`。这是账户配额问题，不是代码 bug——充值或开启付费后即可恢复
- **venv 环境**：测试专用 venv（在本仓库之外）中已将 `transformers` 降级为 4.44.2、`numpy` 降级为 1.26.4，以兼容 torch 2.2.2（重排序/CrossEncoder 依赖）。该 venv 还有 gradio/starlette、langchain-chroma/langchain-core 的版本冲突警告，属既有问题，不影响本应用运行
- **重排序模型**：`BAAI/bge-reranker-v2-m3` 约 2.3GB，首次调用 `rerank_search` 或 `accurate` 管线时自动下载（懒加载），需要网络
- `api/logger_config.py` 第 44 行之后有一段约 70 行的 SLS 远程日志参考文档以 `'''...'''` 字符串形式内嵌，不影响运行但较为混乱，如不需要可删除
- `agent_graph_advanced.py`、`mcp_server.py` 等文件内有多处 `'''...'''` 注释掉的旧实现，属学习保留内容，不影响运行
