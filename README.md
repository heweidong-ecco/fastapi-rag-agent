# RAG Agent API

一个生产级的 RAG（检索增强生成）+ Agent API 服务，集成了混合检索、重排序、查询改写、引用溯源、LangGraph Agent、MCP 工具、Mem0 长期记忆和成本控制等核心能力，构建于 FastAPI、PostgreSQL(pgvector)、Redis 之上。

**模型端点**：生成/对话 LLM 走 **DeepSeek**（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_*` 三键可换任意 OpenAI 兼容端点，见 `api/config.py`）；
Embedding 走 **阿里云百炼 DashScope `text-embedding-v2`**（1536 维）。

## 📊 性能目标（⚠️ **目标值，尚未实测**）

> 🔴 **这三行此前写作"性能指标"，是本仓校对时改的。** 它们**没有任何实测数据支撑** ——
> 仓库里那份 `性能基线报告模板.txt` **只是模板**，从未跑出过报告；
> `ROADMAP.md` 也明写「P99 / 失败率 / 并发 / Grafana **尚无实测数据**」。
> **把它们当指标引用是不诚实的**，故就地改名为「目标值」。
> 📌 反证（单样本，非 P99）：`mode=accurate_norerank` 实测 **1.93s**（含查询改写），**已超过下表的 800ms**。

| 目标 | 目标值 | 现状 |
| :--- | :--- | :--- |
| **P99 检索延迟** | `< 800ms` | ⬜ **未实测**（`mode=fast` 实测 ~25ms；`accurate_norerank` 单样本 1.93s） |
| **基础检索失败率** | `< 0.1%` | ⬜ **未实测** |
| **Embedding 缓存命中率** | `> 90%` | ⬜ **未实测** |
| **多格式文档支持** | PDF, Word, Markdown, HTML | ✅ 已实现（`api/document_parser.py`） |

## 🏗 技术架构

![系统架构图](docs/architecture.png)

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

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/rag-agent-api.git
cd rag-agent-api
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的阿里百炼 API Key 等信息
```

### 3. 一键启动

```bash
docker compose up -d
```

### 4. 验证

```bash
curl http://localhost:8000/health
# 应返回 {"status":"healthy",...}

curl http://localhost:8000/api/v1/
# 应返回 {"status":"ok","version":"v1"}
```

### 5. 访问文档

-   Swagger UI：http://localhost:8000/docs
-   Grafana 监控：http://localhost:3000 (admin/admin)
-   Prometheus：http://localhost:9090

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
├── Agent/                  # Agent 子系统文档
├── docs/                   # 项目文档（FAQ、架构图、Demo）
├── archive/                # 归档的未使用文件（不入库）
├── docker-compose.yml      # 服务编排
├── prometheus.yml          # Prometheus 配置
├── locustfile_v2.py        # 性能压测脚本
└── README.md               # 本文件
```

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
| 4 | **知识库语料为测试数据** | 检索命中的是「测试文档一」「Python是一门强大的编程语言」（`source` = `test`/`test_docs`） | 直接演示会显得**答非所问**；需先灌真实语料 |
| 5 | **本地 Qdrant 是单实例锁** | `mem0_client` 在 `memory_store.py` **模块导入期**就开 `./.mem0/qdrant` ⇒ 应用跑着时 `pytest` 跑不了（`Storage folder … already accessed by another instance`） | 跑测试前须停应用；逃生口：从**仓库根**跑 + 设 `MEM0_DIR=<临时目录>`（**两个都要**） |
