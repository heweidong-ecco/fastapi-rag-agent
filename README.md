# RAG Agent API

> ## 📌 先读这一段：**本仓是「轻量版」**
>
> 本仓是**受硬件条件约束**（本机 8GB 内存 / 4 核）**经过三轮删减**后留下的**可运行最小集**。
> 它**不是**这个项目的全貌 —— **完整版还包含相当一部分本仓里没有的模块与能力**，
> 那些部分**不在本仓的范围内**，也不由本仓的测试覆盖。
>
> **本仓里保留的这部分**，代码有单元测试与模块级测试覆盖，**是可以跑、可以验的** ——
> 下面「快速开始」照做即可，`pytest` 也有可对照的基线数字。
>
> ⚠️ **两点如实说明（别让这段话被误读）**：
> 1. **被删掉的那部分，本仓无法为它背书** —— 它们的可运行性、测试情况都在本仓之外，
>    本仓既看不到、也验不了。**本段只承诺"本仓里的东西能跑"。**
> 2. **删减的直接代价已经登记在文档里**，不是"删掉了但功能照旧"：
>    `mode=accurate/full` 与重排序在本机跑不了（装不下 torch + 2.3GB 模型）；
>    具体清单见下方「📊 性能目标」与「⚠️ 已知限制」。

一个 RAG（检索增强生成）+ Agent API 服务，集成了混合检索、重排序、查询改写、引用溯源、LangGraph Agent、MCP 工具、Mem0 长期记忆和成本控制等核心能力，构建于 FastAPI、PostgreSQL(pgvector)、Redis 之上。

> 🔴 2026-09-20 改：原文首句写「一个**生产级的** RAG + Agent API 服务」——
> **已删去"生产级"**。理由：本仓的性能数字**全部未实测**（见下），
> 且有三条已知限制；把一个没有验收数据的东西称作"生产级"是**没有依据的断言**。

**模型端点**（⚠️ **两件事别混**）：
- **Embedding 固定走** 阿里云百炼 DashScope `text-embedding-v2`（1536 维）。
- **生成/对话 LLM 是可配置的**，而 **`api/config.py` 的默认值是 DashScope + `qwen-turbo`/`qwen-plus`**。
  🔴 **本项目开发机上用的是 DeepSeek**（`.env` 里 `LLM_BASE_URL=https://api.deepseek.com` ·
  `LLM_MODEL_FAST`/`LLM_MODEL_CHAT=deepseek-v4-flash`），但那是 **`.env`（不入库）里的取值**，
  **不是代码默认值** —— **新克隆下来跑的是 qwen，不是 DeepSeek。**
  要切，填 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_FAST` / `LLM_MODEL_CHAT` **四个**环境变量
  （`LLM_API_KEY` 不填则回退用 `DASHSCOPE_API_KEY`）——
  **`.env.example` 第 4–9 行已备好这四个键的注释模板**（默认注释掉 ⇒ 不填就是 DashScope）。

## 📊 性能目标（⚠️ **目标值 —— 不是指标**）

> 🔴 **这三行此前写作「性能指标」，且下面这张表是核对时改的。**
>
> **仓库里【有】一次旧压测记录**（见 `性能基线报告模板.txt`，2026-06-25，三档并发 10/20/35）——
> ⚠️ **但那份记录不能用来支撑这三个数，方向甚至相反**：

| 旧记录（2026-06-25） | 值 | 与下表目标对比 |
| :--- | :--- | :--- |
| P99 延迟 | **68 / 32 / 28 ms**（10/20/35 并发） | **低于**目标的 800ms ✅ |
| **错误率** | **77.24% / 96% / 97%** | 🔴 **远糟于**目标的 `< 0.1%` |
| QPS | 5.1 / 10.5 / 17.8 req/s | — |

> ⚠️ **那次压测跑在坏掉的环境上**：同日 `api/logs/api_2026-06-25.log` 含 **113 条未捕获异常**
> （`redis:6379` 解析失败、`could not translate host name "postgres"`），**与 77–97% 的错误率自洽**。
> ⇒ **P99 那几个数不能采信**（失败请求不产生正常延迟样本），**口径也从未复核过**。
>
> 📌 **所以本表的每一格「现状」都是 ⬜**：不是"没有记录"，而是 **"那份记录不可用"**。
> `ROADMAP.md` 里那句「P99 / 失败率 / 并发 / Grafana **尚无实测数据**」指的正是这个意思
> （核查清单 24 项**全部未勾**）。

| 目标 | 目标值 | 现状 |
| :--- | :--- | :--- |
| **P99 检索延迟** | `< 800ms` | ⬜ **无可采信数据**（旧记录 28–68ms **跑在坏环境上**，不可用） |
| **基础检索失败率** | `< 0.1%` | 🔴 **旧记录 77–97%（环境坏，不可用；但说明这条从未达标过）** |
| **Embedding 缓存命中率** | `> 90%` | ⬜ **未实测** |
| **多格式文档支持** | PDF, Word, Markdown, HTML | ✅ 已实现（`api/document_parser.py`） |

## 🏗 技术架构

![系统架构图](docs/architecture.png)

**整套系统架构图**（上面那张没画到的部分：MCP 工具层 · 部门制 Agent · 成本控制体系）：

![完整系统架构图](docs/architecture-full.png)

> 📌 **2026-09-20**：这张图原在 `Agent/docs/architecture_full.png`，随 `Agent/` 目录处置搬到 `docs/`。
> 它是**整套系统**级别的图（另一张 `docs/architecture.png` 只到子系统级）。
>
> ✅ **已逐项核对，图上组件本仓都有**：
> FastAPI 网关（路由/认证/限流/日志/文本规范化）· LangGraph **部门制 Agent**
> （Supervisor + 检索/计算/日期/翻译/ReAct + Checkpointer —— `api/agent_graph_advanced_learning.py:105/134/154/169/197/246`）
> · **MCP Server 工具注册中心**（`api/mcp_server.py:24`）· RAG 检索管线 · Mem0 / Redis / pgvector
> · **成本控制体系**（`api/cost_dashboard.py`）· Grafana + Prometheus（`docker-compose.yml:90`）。
>
> ⚠️ **一处已过时，别照图核代码**：图上工具层画的是 **`rag_search`**，而当前的实际工具是
> **`fetch_webpage_html`**（`api/agent_graph_advanced_learning.py:47-51`）。⇒ 这张图记录的是**更早一代**的工具集。

## ❓ 常见问题

遇到问题请先查阅 [FAQ 与故障排查](docs/FAQ.md)。

## 🛠 技术栈

| 类别 | 技术 | 说明 |
| :--- | :--- | :--- |
| **Web框架** | FastAPI | 高性能异步API框架 |
| **数据库** | PostgreSQL + pgvector | 关系型数据库 + 向量检索 |
| **缓存** | Redis | Embedding缓存、工具调用缓存、限流计数器 |
| **重排序** | BGE-Reranker | Cross-Encoder模型，提升检索精度 |
| **监控** | Prometheus + Grafana | 指标采集与可视化大屏 |
| **容器化** | Docker + Docker Compose | 一键部署 |
| **测试** | pytest + Locust | 单元测试、集成测试、性能压测 |
| **评估** | RAGAS | 自动化检索质量评估 |
| **CI/CD** | GitHub Actions | 自动测试工作流 |

## ✨ 核心功能

-   **多模态检索**：支持 `fast`（快速）、`accurate`（精确）和 `full`（完整）三种模式，可灵活组合向量检索、BM25关键词检索、RRF融合和Cross-Encoder重排序。
-   **查询改写**：利用LLM对用户问题进行上下文补全和指代消解，显著提升多轮对话场景下的检索准确率。
-   **引用溯源**：答案自动标注信息来源，支持点击溯源到原始文档块。
-   **流式输出**：基于SSE实现逐字生成，支持真中断，避免Token浪费。
-   **认证与权限**：支持API Key和JWT双认证，三级权限控制（管理员/付费用户/免费用户）。
-   **限流与配额**：令牌桶限流 + 每日配额控制。
-   **多格式文档**：支持PDF、Word、Markdown、HTML，含复杂PDF表格和双栏解析。
-   **Agent 能力**：LangGraph 多分支路由、MCP 工具协议、Plan-and-Execute、Mem0 长期记忆、Token 成本控制。

## 📈 评估体系

-   **自动评估**：集成 RAGAS，自动评估忠实度、答案相关性、上下文召回率和精确率。
-   **人工评估**：从完整性、简洁性、逻辑性、可用性四个维度进行定性分析。
-   **Bad Case分析**：持续跟踪并分析失败案例，驱动系统优化。

## 🚀 快速开始

**前置要求**（⚠️ 2026-09-20 补 —— 原先没写，而 Python 版本是**硬要求**）：

| 需要 | 说明 |
|---|---|
| **Python 3.10** | ⚠️ **必须是 3.10**（`api/Dockerfile` 的基础镜像也是 3.10）。**不要用 `python3`** —— 本机实测 `python3` = **3.14.7**，只有 `python3.10`（3.10.10）可用。命令一律写 `python3.10 -m venv venv` |
| **Docker + Docker Compose v2** | 只用来跑 PostgreSQL 与 Redis（路径 A 不构建镜像） |
| 磁盘 / 内存 | 轻量路径几百 MB 即可；**路径 B（Docker 全量）要下 GB 级镜像，8GB 内存的机器上会失败** |

### 1. 克隆项目

```bash
git clone https://github.com/heweidong-ecco/fastapi-rag-agent.git
cd fastapi-rag-agent
```

> 🔴 2026-09-20 修：此处原为 `git clone https://github.com/你的用户名/rag-agent-api.git`
> —— **是占位符，照抄必然 `Repository not found`**（已实测）。现改为真实地址。

### 2. 配置环境变量

```bash
cp .env.example .env
# `api/config.py` 的 validate_config 检查【四项】—— 缺任何一项都【拒绝启动】：
#   DASHSCOPE_API_KEY   —— Embedding 用（阿里百炼）
#   POSTGRES_PASSWORD   —— ⚠️ 这一项容易漏！.env.example 里给了个占位值 mysecretpassword，
#                          不改成真的也能起来（本地 Docker 就是那套），但**不能删/留空**
#   JWT_SECRET_KEY      —— 随便一串随机值
#   LOGIN_PASSWORD      —— 管理员登录口令
# 生成随机值：python3 -c "import secrets; print(secrets.token_urlsafe(24))"
#
# 生成/对话 LLM 默认走 DashScope 的 qwen-turbo / qwen-plus；
# 想换成 DeepSeek 等 OpenAI 兼容端点，取消 .env.example 第 4–9 行的注释并填 LLM_* 四键。
```

> 🔴 2026-09-20 修：此处原写「**三项**」——**漏了 `POSTGRES_PASSWORD`**。
> 实测 `api/config.py:58-74` 检查的是 **4 项**；漏写会让"删了这一项 ⇒ 起不来 ⇒ 按本表查不到原因"。

### 3. 启动

本仓有**两条**路径。**推荐第一条**：它不需要构建镜像，在 8GB 内存的机器上也能跑。

#### ✅ 路径 A · 轻量（推荐）—— DB/Redis 用 Docker，API 跑在本机

```bash
# 3a. 起 DB 与 Redis（这两个是现成镜像，不触发构建）
docker compose up -d postgres redis
#     ⚠️ 但如果 docker ps 里已经有 postgres-rag / redis-rag，【别跑这句】——
#        见下方「⚠️ 3a 的前提」：它们可能属于别的 compose 项目，up 会撞名或重建。

# 3b. 建虚拟环境并装依赖
python3.10 -m venv venv
venv/bin/pip install -r api/requirements-test.txt      # ← 注意是 -test 那份

# 3c. 起 API（在 api/ 目录下！）
cd api
ENABLE_DASHBOARD=false ../venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

#### ⚠️ 3a 的前提：**先看容器是不是已经有了**

```bash
docker ps --format '{{.Names}}' | grep -E 'postgres-rag|redis-rag'
```

| 结果 | 该怎么做 |
|---|---|
| **有**（已存在） | **用 `docker start postgres-rag redis-rag`** —— ⛔ **不要** `docker compose up` |
| **没有** | `docker compose up -d postgres redis` 才是对的（全新机器） |

> 🔴 **为什么要分这两种（2026-09-20 实测）**：
> `docker compose up` 是**按 compose 项目**工作的，而容器可能**不属于本项目**。
> 实测本机：`postgres-rag` / `redis-rag` 的 `com.docker.compose.project` 是 **`my-fixed-name`**、
> `config_files` 指向**另一个仓库**的 compose 文件；本仓 `docker compose ps` **是空的**（不认领它们）。
> 此时 `docker compose up -d postgres redis` 的 `--dry-run` 会计划 **`Container postgres-rag Creating`**
> + 建两个新网络 ⇒ **要么撞名硬失败，要么把容器重建到 `fastapi-rag-agent_app-net`**。
> ⛔ **而后者正是本仓的红线** —— `agent-eval-gate` 的评测 harness 默认用旧网络名
> `my-fixed-name_app-net`（见 `docker-compose.yml` 末尾「改名后遗症」），**重建会打断它**。
> ⇒ **已有容器就 `docker start`**（重启现有容器，网络与端口都不变）。

> 🔴 **为什么用 `requirements-test.txt` 而不是 `requirements.txt`**：
> 后者含 `sentence-transformers` / `transformers` / `camelot-py[cv]` / `opencv-python`
> —— **拖 GB 级的 torch**。而**本仓默认路径不需要 torch**：默认检索模式是
> `accurate_norerank`，`api/reranker.py:14` 对 `sentence_transformers` 是**真懒加载**。
> **代价（已登记）**：`mode=accurate` / `mode=full` 与 `/rag/rerank_search` **在本机跑不了**（要装 torch + 2.3GB 模型）。
> 完整说明见 `api/requirements-test.txt` 头部注释。

> ⚠️ **必须在 `api/` 目录下起 uvicorn** —— 有一处路径是按相对位置解析的（本仓已把 MCP 那条修成绝对路径，
> 但习惯上仍建议 `cd api`）。`bash dev.sh` 就是干 3a+3c 这两步的（但它假设依赖已装好）。

#### 🐳 路径 B · Docker 全量

```bash
docker compose up -d
```

> ⚠️ **它会 `build` API 镜像**（`docker-compose.yml:13` 的 `build: context: ./api`），
> 而 `api/requirements.txt` 含 torch 系 ⇒ **拉几个 GB、构建很久**。
> **8GB 内存 / Docker 配额较小的机器上大概率失败**（实测本机不行）。**只有要跑重排序或追求一条命令时才选它。**

### 4. 验证（**以下输出是 2026-09-20 实测的原文**）

```bash
curl http://localhost:8000/health
# {"status":"healthy","checks":{"database":"ok","redis":"ok","embedding_api":"deferred to external monitoring"}}

curl http://localhost:8000/api/v1/
# {"status":"ok","version":"v1"}

curl http://localhost:8000/ready
# {"status":"ready"}      ← ⚠️ 启动后 10 秒内会返回 503，那是设计行为，不是坏了
```

再取个 token、跑一次真实检索（**这才是"真的跑起来了"**）：

```bash
# ⚠️ 先把 .env 里的值载进当前 shell —— 下面两行【原本没写，照抄会拿到空口令 ⇒ 401】
set -a; . ./.env; set +a          # 或者手写：export LOGIN_USER_NAME=admin LOGIN_PASSWORD='你的口令'

TOK=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"user_name\":\"$LOGIN_USER_NAME\",\"password\":\"$LOGIN_PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s -X POST localhost:8000/api/v1/rag/hybrid_search -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"question":"测试","top_k":3}'
# 应返回 {"method":"hybrid (vector + bm25)","docs":[...]} —— docs 里的 "from" 字段是 "vector"/"bm25"/"both"
```

> 🔴 2026-09-20 修：`$LOGIN_USER_NAME` / `$LOGIN_PASSWORD` **只存在于 `.env`，它们不是 shell 变量**
> —— 原版没写怎么把它们导出来，照抄会发出**空用户名/空口令**（`TOK` 取不到，下一句 401）。
> **这正是本 PR 要消灭的那类"照抄跑不通"。** 已补 `set -a; . ./.env; set +a`。

> ⚠️ **此时知识库是空的**（新装的库没有文档）⇒ `docs` 会是 `[]`，**这是正常的**。
> 要看非空结果，先按 `docs/demos.md` 灌几篇文档，或参考 `/api/v1/rag/insert`。

### 5. 访问文档

-   Swagger UI：http://localhost:8000/docs
-   Grafana 监控：http://localhost:3000 (admin/admin) —— ⚠️ **仅路径 B 会起它**（路径 A 只起 postgres/redis）
-   Prometheus：http://localhost:9090 —— 同上

## 🤖 用另一个 Agent 来测这个项目？

见 **`docs/给Agent的测试与调试指南.md`** —— 里面有可直接粘贴的 Prompt、分层命令行、每个失败的已知原因。

## 📁 项目结构

```
.
├── api/                    # 应用代码
│   ├── main.py             # FastAPI 应用入口
│   ├── api_v1.py           # V1 版本路由
│   ├── rag_pipeline.py     # 综合检索管线
│   ├── reranker.py         # Cross-Encoder 重排序
│   ├── query_rewriter.py   # 查询改写
│   ├── hybrid_search.py    # 混合检索
│   ├── db.py               # 数据库操作
│   ├── cache.py            # Redis 缓存
│   ├── config.py           # 环境变量集中管理
│   ├── exceptions.py       # 错误码与异常定义
│   ├── schemas.py          # Pydantic 模型
│   ├── deps.py             # 依赖注入
│   ├── chunker.py          # 文档分块
│   ├── document_parser.py  # 多格式文档解析
│   ├── document_preprocessor.py # 文档预处理管道
│   ├── rate_limiter.py     # 令牌桶限流
│   ├── quota_limiter.py    # 配额管理
│   ├── metrics.py          # Prometheus 指标
│   ├── auth.py             # 认证逻辑
│   └── ...                 # 更多模块
├── docs/                   # 项目文档（FAQ、架构图、Demo、决策记录）
├── archive/                # 归档的未使用文件（不入库）
├── docker-compose.yml      # 服务编排
├── prometheus.yml          # Prometheus 配置
├── locustfile_v2.py        # 性能压测脚本
└── README.md               # 本文件
```

> 📌 **关于原 `Agent/` 目录（2026-09-20 已处置）**
>
> 本仓是在**原系统**的基础上做的。原系统是**极狐 GitLab 上的 `agent-assistant` 项目**
> （证据：原系统文档里的 `git clone https://jihulab.com/…/agent-assistant.git`，见 git 历史 `351f699` / `2c1a922`）。
> 它的文档曾以 `Agent/` 目录形式随仓携带，2026-09-20 因**与仓根文档大面积重复、且其 `.env.example`
> 与 `deploy.md` 会误导**（前者配置面与仓根不同、后者是占位符 URL）而拆解处置：
> **架构图搬进 `docs/`，Agent 排障 9 条并入 `docs/FAQ.md` 第五节，其余删除。**
> 全部原文仍在 git 历史里（`git show 351f699 --stat`）。

## 📄 许可证

**MIT License** —— 全文见 [`LICENSE`](LICENSE)。

> 🔴 2026-09-20 补：本行此前只写「MIT License」而**仓库里没有 `LICENSE` 文件**
> （GitHub API 的 `license` 字段也是 `null`）—— **声明与事实不符**。现已补上文件。

> 一键部署文件：[deploy.md](deploy.md)

## ⚠️ 已知限制（诚实清单）

> 📌 本仓立过一条规矩：**「后果性断言必须有一条当场可跑的命令支撑」**。
> 下面几条是**已知不达标**的地方，写在这里免得被当成"已实现"。

| # | 限制 | 实测证据 | 影响 |
|---|---|---|---|
| 1 | **浏览器工具在本机不可用** | `venv/bin/playwright install chromium` ⇒ `ERROR: Playwright does not support chromium on mac13`（本机 macOS **13.6**；Playwright 1.62 要 chromium **1234**，缓存里是 1228） | `fetch_webpage` / `screenshot_webpage` 健康检查恒为 unhealthy（**环境天花板，非代码缺陷**）—— 目前工具健康 **4/6** |
| 2 | **`mode=accurate/full` 与重排序未验** | 本机 **8GB 内存 / 4 核**，装不下 torch + `bge-reranker-v2-m3`（2.3GB） | 默认模式是 `accurate_norerank`（**不碰 torch**），故产品可用；但这两条路径**本机验不了** |
| 3 | **性能数字全部未实测** | 见上方「性能目标」段 | 不得作为选型/承诺依据 |
| 4 | **知识库语料良莠不齐** | `documents` 表 **35/77 行是测试数据**（`source` = `test` 24 行 + `test_docs` 11 行），含「测试文档一」这类；其余是正经语料 | 结果**时好时坏** —— 同一个问题可能命中切题的（如 `eval_dataset.json#23`）也可能命中测试垃圾。**演示前建议先灌一份干净语料** |
| 5 | **本地 Qdrant 是单实例锁** | `mem0_client` 在 `memory_store.py` **模块导入期**就开 `./.mem0/qdrant` ⇒ 应用跑着时 `pytest` 跑不了（`Storage folder … already accessed by another instance`） | 跑测试前须停应用；逃生口：从**仓库根**跑 + 设 `MEM0_DIR=<临时目录>`（**两个都要**） |
