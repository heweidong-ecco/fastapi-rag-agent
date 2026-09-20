# Changelog

All notable changes to this project will be documented in this file.

> **起点说明**:本文件自 **2026-09-15** 起建立。**此前的项目历史以 `git log` 为准,不追溯补写** —— 避免编造未曾记录过的条目。
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。本仓库当前无版本标签,故条目一律记在 `[Unreleased]` 下。
> 相关机制:决策进 `docs/decisions/`、过程错误进 `docs/复盘/`、改动进本文件(见 `ROADMAP.md`「当前指针」)。

## [Unreleased]

### Added

- 🔴 **"别人 clone 下来能不能跑" —— 实测后发现【不能】，已修**（2026-09-20）。

  **业务方问「README 等等别人 git clone 工作都做好了吗」—— 我去真 clone 了一遍，答案是"没做好"：**

  | 步 | 原文 | 实测 |
  |---|---|---|
  | 1 | `git clone https://github.com/你的用户名/rag-agent-api.git` | ❌ **`Repository not found`** —— **占位符 URL**，照抄必失败 |
  | 3 | 「一键启动」= `docker compose up -d` | ⚠️ 它会 **build 多 GB 镜像**（`docker-compose.yml:13` 的 `build: context: ./api`，而 `api/requirements.txt` 含 torch 系）⇒ **8GB 内存上跑不动（实测）**，与"一键"的描述严重不符 |
  | — | **无任何依赖安装步骤** | ❌ README 全文 grep `pip install`/`requirements` = **0 命中** |
  | — | **`dev.sh` 一次都没提** | ❌ 文件在仓库里，且它正是本仓的本地开发路径 |
  | — | **`requirements-test.txt`（轻量路径）没提** | ❌ **本仓其实有两条路径**，README 只暗示了重的那条 |

  **修法**：
  1. **README 快速开始重写** —— 真实 clone URL；**两条启动路径**（**路径 A 轻量**为默认：
     `docker compose up -d postgres redis` + `pip install -r api/requirements-test.txt` + 本地 uvicorn；
     路径 B Docker 全量，并明写它的构建代价）；提 `dev.sh`；
     **验证步骤给出 4 条命令 + 2026-09-20 实测输出原文**（含"库是空的 ⇒ `docs: []` 是正常的"这类坑）；
     末尾指向新的 Agent 指南。
  2. **`docs/FAQ.md` 补 Q1.1–Q1.5** —— 原 FAQ **整份假设 Docker 路径**（Q1–Q3 全是 `docker compose`），
     新增：轻量路径怎么跑 / `Repository not found` / Postgres 连不上（且**要用 `docker start` 而非 `up`**）/
     `validate_config` 的**四个**必填项 / `pytest` 撞 Qdrant 单实例锁的逃生口。
  3. **新增 `docs/给Agent的测试与调试指南.md`** —— 面向**另一个 Agent**：
     可粘贴的 Prompt ×3 · 分层命令行与 marker 对照 · **「看起来像坏了其实不是」对照表（10 条）** ·
     日志定位法 · **红线 6 条**（别 build 镜像 / 别不带 `rag_test` 跑真库 / 别直推 main / …）· 提交前必跑凭据门。

  **同一批的诚实修正**：README 里 `curl /api/v1/` 应返回 `{"status":"ok","version":"v1"}` —— **这条原本就是对的**
  （实测确认），未改。

- **第 0 步「盘点」三件产出 —— 为的是"改 A 漏 B"这类问题**（2026-09-20）。

  业务方指出一个更根本的隐患：**「你对整个项目还没有完全看透，等下修了这边，又漏那边」**。
  ⇒ **先盘点再动手**，产出三件：

  | 产出 | 路径 | 作用 |
  |---|---|---|
  | **断言总表** | `docs/断言总表-2026-09-20.md` | 把"看透代码"换成"**核断言**"：交付文档 3 份共 **33 条**断言，每条带**当场可跑的核对命令**（已核 12 条，其余标 ⬜ 并写明缺什么；§B–§E 登记为欠账，**不自称完整**） |
  | **影响面扫描器** | `scripts/impact.sh` + 回归 **11 项** | **改动前的机械防线**：列出全仓谁会因这次改动而变成错的 |
  | **重写保留清单** | `docs/PR34-重写保留清单-2026-09-20.md` | 把 `694d424` 里**方向无关、已实测**的内容摘出来 ⇒ 重写时不会丢实测 |

  **盘点当场核出 6 条原审计没有的问题**（N1–N6，详见 `docs/待办登记-2026-09-20-全仓审计与方向更正.md` §十一）：
  🔴 README 论证「P99 不可采信」所依赖的日志**克隆者拿不到**（`.gitignore:9 logs/`，`git ls-files api/logs/` = 0）·
  ~~🔴 FAQ 说 `-test` 是「只做减法」**不成立**~~ ⚠️ **此条已于同日撤回 —— 是错的**，见下方 `Fixed` 段 ·
  ⚠️ `Agent/` 是审计的整片盲区 · ⚠️ 技术栈表列 RAGAS/Locust 而轻量路径装的没有 ·
  ⚠️ 根级 2 个 md 被 gitignore 但在盘上 · ⚠️ `/rag/search` 对无效 mode **静默兜底**（多花钱、多延迟）。

- **`docs/FAQ.md` 新增「五、Agent 相关」A1–A9**（2026-09-20）。原系统 `Agent/docs/faq_agent.md` 的 Q7–Q15 迁入
  —— **根 FAQ 此前 0 条 Agent 排障**。⚠️ 迁入时**逐条核了代码**，其中**原 Q13（让人查 `.env` 的 `MEM0_API_KEY`）
  与 Q14（说可调 Mem0 的 `delete()`）两条在本仓不成立**，已按事实改写（本仓 Mem0 是**本地模式**，
  没有那个键；`api/memory_store.py` 也**没有** `delete` 方法）。Q1–Q6 与根 FAQ 逐条重复、Q16 与根 Q10 重复，**未迁**。

### 说明

- 本条的**发现方式**值得记：我是**真去 `git clone` 了一遍、照着 README 盲跑**才发现的。
  在这之前我已经在同一个 PR 里把 README 改成"诚实版"、并写了「已知限制」——
  **却从没验过"照 README 做能不能跑起来"**。⇒ **"诚实化"不等于"可用"。**

- **`LICENSE`（MIT）+ README「已知限制」诚实清单**（2026-09-20 · B 档：技术预览 Release 的前置）。

  **为什么补 LICENSE**：README 一直写「MIT License」，但**仓库里没有这个文件**
  （GitHub API 的 `license` 字段是 `null`）—— **声明与事实不符**。一个 public 仓要给别人用，这是硬缺口。

  **README 改了三处**：
  1. 🔴 **「性能指标」→「性能目标（⚠️ 目标值 —— 不是指标）」**：
     `P99<800ms` / `失败率<0.1%` / `缓存命中率>90%` 三行**不能作为指标引用**。
     ⚠️ **合并前评审纠了我一处**:我初稿写「`性能基线报告模板.txt` **只是模板**，从未跑出过报告」
     —— **那是假的**。该文件里有**三份 2026-06-25 的实测**（10/20/35 并发，
     **P99 68/32/28ms，错误率 77.24% / 96% / 97%**）。
     ⇒ 已改为**据实呈现**:那是**跑在坏环境上的一次压测**（同日 `api_2026-06-25.log` 有
     **113 条未捕获异常**：redis/postgres 解析失败，与 77–97% 自洽），
     **P99 那几个数不可采信**，但**「失败率 77–97%」这条更糟的已知事实不该被说成"未知"**。
     📌 **这正是本 PR 立的那条规矩（"断言必须有据可查"）的反面 —— 我在讲道理的段落里写了条没核过的断言。**
  2. **模型端点描述过时且"只在开发机成立"**：原文写「LLM/Embedding 由阿里云百炼 DashScope 提供」，
     而开发机的 `.env` 已把生成/对话 LLM 换成 **DeepSeek**（DEC-017 裁决 ②）。
     ⚠️ **但那是 `.env`（不入库）的取值，不是代码默认值** —— `api/config.py:52-55` 的默认仍是
     DashScope + `qwen-turbo`/`qwen-plus` ⇒ **新克隆下来跑的是 qwen**。
     已改为**把这两件事分开写清**，并说明 `.env.example:4-9` 已备好 `LLM_*` 四键的注释模板。
  3. **新增「⚠️ 已知限制（诚实清单）」段**（5 条）：浏览器工具在本机不可用 ·
     `accurate/full` 与重排序未验 · 性能数字全部未实测 · **知识库语料是测试数据** · 本地 Qdrant 单实例锁。

  **顺带修**：仓库描述里的错字 `Memd` → `Mem0`（并去掉一个多余空格）。

  **`docs/demos.md` 也补了一段【实测可跑】**：原文三个场景的命令是 `curl -X POST "..."` **占位**、
  且从未实测；新增段落给出**当场验过的真命令与真输出**（含最容易翻车的点：
  `generate_answer` / `citations` **默认 false**，不打开就只有 docs 没有答案）。

- **⑦ M6 · `/rag/search` 单模块测试闭环 —— 本仓第一条「改代码 → 跑测试 → 看结果」的闭环先例**（2026-09-17）。
  新建 `api/test_rag_search.py`（**22 条**：21 离线 + 1 集成）· `api/pytest.ini` · `ci.yml` 增加第二个 job。决策见 `DEC-013`。

  **靶子** = `/rag/search`。`CODE_INVENTORY.md:159` 建议二选一，另一条「最终留下的那套 Agent」**被两条同时挡死**：
  ① M5 组 1 的 C 档裁决未做（`ROADMAP.md:18`：Agent 不代判）② 它要 chat LLM，而 qwen-turbo/plus **免费额度已耗尽** ⇒ **跑不通 = 没有闭环**。
  而 `/rag/search` 实测跑通（`mode=fast` → 200 / 825ms / `docs[0].from == "both"`，**RRF 真的融合了**），
  **不碰 torch、不调 chat LLM**。🔴 **而它此前测试覆盖是 0**（`test_search.py` 测的是 `/rag/pg_search`），
  **RRF 恰恰是 2026-08-17 复审出 bug 的地方**（§0-4）。

  | 层 | 测什么 | 需要 | 进 CI |
  |---|---|---|---|
  | **L0** 纯逻辑 | `_rrf_fusion` 融合/排序/截断/空输入 · 四个 factory 开关矩阵 | 只要 langchain | ✅ |
  | **L1** 契约 | 401 · `top_k` 422 边界 · `mode` 是 query 参数 · 缺字段 422 | **redis** | ✅ |
  | **L2** 行为 | **mode→pipeline 分派** · RRF 穿到 HTTP 层 · `top_k` 传递 · 响应形状 | redis + patch 6 个缝 | ✅ |
  | **L3** 集成 | 真 pgvector + 真 BM25 + 真 DashScope embedding | postgres + 外网 | ❌ `@pytest.mark.integration` |

  - **变异测试：证明新套件真有牙**（用例能过 ≠ 能红）——三个变异各自精确命中：

    | 变异 | 结果 |
    |---|---|
    | A · 路由 `if mode == "fast"` 改坏 | **1 failed**，正好是 `[fast-False-False-False]` 那一格 |
    | B · RRF 两路命中误标成 `vector` | **2 failed**，正好是融合那条 + HTTP 形状那条 |
    | C · **按 3 元组解包**（=2026-08-17 真 bug 的形状） | **11 failed**，`ValueError: too many values to unpack`，L0 与 L2 双层都红 |

  - 全套回归：**59 passed / 1 skipped**（基线 37+1，**+22 条新测试，零回归**）；`routes=14` / `OPENAPI_PATHS=59` 逐位未变

- 🔴 **修掉一个会挂死 CI 的已存在缺陷：`import main` 会起非 daemon 遥测线程，导致"测试全过但进程退不出去"**（2026-09-17 · M6 期间实测发现）。

  **病因**：`cost_dashboard.py:218` 在**导入期**就建 Gradio Blocks ⇒ 只要 `import main`，Gradio 就起线程去连
  `huggingface.co` 发匿名遥测（`gradio/analytics.py` → `huggingface_hub._telemetry`），外加两条 `posthog/consumer.py` 上报线程。
  **网络不通时它们卡在 TCP connect 上永不返回**，主线程永远停在 `threading._shutdown`。

  | 实测 | 结果 |
  |---|---|
  | 不设开关 | **20s+ 进程不退出**（此前一直如此，只是没人量过） |
  | 设 `GRADIO_ANALYTICS_ENABLED=False` | **11s 内正常退出**（其中 `import main` 本身 6.6s） |
  | 修复后残余**非 daemon** 线程 | **0** |

  **修法**：`api/conftest.py` 在 `import main` **之前**设 `GRADIO_ANALYTICS_ENABLED=False`。
  ⚠️ **位置不能挪到各测试模块里** —— `conftest.py` 先于所有测试模块被导入，那里才是唯一有效的时点。
  ⚠️ 它**随机复现**（取决于当次 DNS/TCP 是快速失败还是挂住）—— 按"跑一次看看"的方式验，大概率显示正常。详见 `docs/复盘/2026-09-17-看到汇总行就以为跑完了.md`。

- **`ci.yml` 增加 `offline-tests` job —— `ci.yml:4` 那句「等本项目重构定案后再接入 —— 见 M6」兑现**（2026-09-17）。
  跑 `pytest api/test_rag_search.py -m "not integration" -v`；带 **redis service**（`redis:7`，零迁移零数据零种子）。
  - 🔴 **redis 不是可选项**：`RateLimitMiddleware` 对每个非公开路径都打 Redis，且 `rate_limiter.py` **没有 `except RedisError`** ⇒ **Redis 不通时全站 500**（实测）。
  - **postgres 不需要**（实测：把 `POSTGRES_PORT` 指向死端口，L1/L2 全绿）—— 断言要么在中间件层、要么在 handler 之前被挡下，要么把库调用 patch 掉了。
  - `import main` 在导入期构造 OpenAI 客户端，**空 key 会抛 `OpenAIError`**（实测）⇒ CI 给**非空 dummy 环境变量**（离线用例永不真调用）。
  - **未接进 CI 的已登记**：L3 集成层 · 既有测试里**另有 27 条也是离线的**（死 postgres 下 48 passed，其中 21 条来自新文件）。

- **`scripts/check_secrets.sh` —— 凭据门（命中即 `exit 1` 中止）**（2026-09-17）。

  **起因是一次真实事故**:当天我把 **3 个历史泄露凭据的字面量写进了 PUBLIC 文档**,
  而**手敲的凭据 grep 报了 `hits=1`×3 却照样让 commit 落地了** ——
  **它只打印,不中止。那不是门,是一份报告。**

  > 🔴 **判据 vs 动作** —— 本仓第 N 次栽在同一个坑上(前有 `LEARNING_INDEX.md`、8 个 PR 跳过留痕门、A 级 skill 命中 0 次)。
  > ⚠️ **同一事故的第 3 次**是在**起草 PR 正文**时又写了一遍,被**外部分类器**拦住 —— **是外面的门救的,不是我的门。**

  | 设计点 | 做法 |
  |---|---|
  | **脚本自身不得含凭据** | 真实凭据从 `.env` **现读**;存量黑名单从 `.secret-denylist` 现读(**该文件也被 gitignore** —— 否则就是拿泄漏源去防泄漏) |
  | **报告只写名字** | 命中时打印 `POSTGRES_PASSWORD` 这样的**键名**,**绝不打印值**(打印了这份日志本身就成了新泄漏源) |
  | **三类检查** | ① `.env` 真实凭据 ② `.secret-denylist` 存量字面量 ③ 通用模式(`sk-` / `ghp_` / `AKIA` / PEM / 裸 JWT) |

  **验证 —— 三条路径都实测过**:
  | 用例 | 结果 |
  |---|---|
  | 通用模式命中(`AKIA…`) | **exit 1** ✓ |
  | **用 `.env` 里的真实凭据做样本** | **exit 1**,且**只报 `POSTGRES_PASSWORD` 这个名字** ✓ |
  | staged 为空 | **exit 0** ✓ |

  - 🔴 **门第一次真上岗,就抓到了【它自己的设计缺陷】**:
    v1 扫的是**整份 diff**(含 `-` 删除行)。于是当我在**删掉** `CODE_INVENTORY.md` 里那处存量字面量时,
    门**报了红** —— 因为我正在删它。
    **"删掉密钥"是好事,不该拦。** ⇒ 已改为**只扫新增行**(`git diff --cached | grep '^+'`)。
    📌 **泄漏只可能发生在"写进去"的时候** —— 这是 v1 没想清楚的一句话。
  - 修后重测四条:**本次提交 exit 0** · **删除行不再触发**(复核该删除行确实还在 diff 里,计数 1)·
    通用模式 exit 1 · **真实凭据 exit 1 且只报名字**。

  - ⚠️ 顺带记一个**测量错误**:我第一次测退出码时写成 `bash ... | tail`,拿到的是 **`tail` 的退出码** ⇒ 显示 `exit=0`。
    **差点据此把"门有效"误判成"门失效"。** 与当天那份 `grep模式写错` 复盘是同一类错。
  - `docs/CODE_INVENTORY.md:31` 那处 **09-15 就存在**的 dev 默认值字面量**已一并脱敏**（改为只写名字）。
    该值**已随 PR #6 从代码移除**,但**字面量不该留在 PUBLIC 文档里,与它是否还活着无关**。

- **PR 纪律新增一道门**：⛔ **开 PR 前必须先跑 `/留痕-checks`**（用户级 skill，查 8 项：commit 规范 / 密钥 / 误提交 / CI / issue 关联 / **Agent 变更回归** / eval-gate / 敏感文件）。写在 `ROADMAP.md` 的 PR 纪律里。
  - 起因：本会话此前 **8 个 PR 一次都没跑过它** —— 我手工维护了 CHANGELOG / `docs/复盘` / 计划进度，**却绕开了业务方为同一目的准备的现成机制**。根因是**门没挂在我会读到的纪律条目里**（PR 纪律我读了 8 遍、每遍都合规，但那条纪律里从头到尾没提这个 skill）。
  - 复盘：`docs/复盘/2026-09-16-八个PR跳过了留痕门.md`（含 8 个 PR 的**回溯体检表**）
- **eval 回归证据**（`agent-eval-gate` · `run=20260916-013720-0e97b254`）：

  | 项 | 值 |
  |---|---|
  | 达标率 | **48/48 = 1.00**（阈值 ≥0.95） |
  | 红队突破 | **0**（硬门） |
  | 判分器 | `deepseek-v4-flash@https://api.deepseek.com`（45 次调用 / 34495 tokens） |
  | SUT | `http://localhost:8000` · mode `accurate_norerank` · **当前代码**（OpenAPI 59 路径） |
  | 结论 | **exit 0 · 通过评测门** —— 与历史基线同口径同结果 |

  - ⚠️ **方法论留痕**：先用 `--offline`（FakeJudge）跑得 **47/48**，换回真实判分器后 **48/48** —— 差异**全部来自判分器口径**，与代码无关。**两轮不同判分器的结果不可比**，引用达标率必须同时给出判分器。
  - 这是**本项目第一次让评测打到当前代码**（此前所有轮次打的是那张 2026-07-01 的镜像，它缺整个 Agent 子系统）。做法：`docker stop rag-api-eval` → 用本仓 venv 原生起 `uvicorn main:app --port 8000` → 评测指向 `localhost:8000`。

- **`docs/重构计划-2026-09-15.md`** —— **当前最高优先级**（业务方 2026-09-15 批准）。含一条**前提级更正**：本机**能跑测试**（曾误判为"做不了运行期验证"）。执行顺序 **基线 → 修 bug → 归档 → 切模块 → M6**，与旧计划相反。同时挂进 `CLAUDE.md` 顶部与 `ROADMAP.md`「当前指针」最上方。
- **`api/requirements-test.txt`** —— `requirements.txt` 的**剔重版**（**只做减法，未加任何新包**）：剔除 `sentence-transformers`（拖 torch）、`transformers`、`camelot-py[cv]`、`opencv-python`、`ragas`、`datasets`、`locust`。剔除依据：`api/` 下**顶层 import 命中 0 次**（`sentence_transformers` 那 2 处是函数内懒加载：`reranker.py:14`、`document_preprocessor.py:171` 且带 try/except）。**代价**：`mode=accurate/full` 与 `rerank_search()` 在本环境跑不了（默认 `accurate_norerank` 不碰 torch）。
- **本仓隔离测试环境** `venv/`（Python 3.10.10，**不入库** —— `.gitignore:2` 已覆盖）。用途：跑 `pytest api/` 与 `import main`。
- **CI 骨架** `.github/workflows/ci.yml` —— 跑 `python -m compileall api/ -q`,Python 钉 **3.10**(与 `api/Dockerfile` 的基础镜像一致,否则"本机能跑、容器里 SyntaxError"拦不住)。**暂不含 pytest** —— 待本项目重构/裁决定案后接入。首次运行 `success`(run `34966390842`,commit `9c844aa`)。
- **`ROADMAP.md`** —— 接续锚点:当前指针 / 交接 / 里程碑 M0–M7 / 已登记待办。格式对齐 `agent-eval-gate`、`product-agent-dev-os`。
- **`docs/CODE_INVENTORY.md`** —— M5 代际盘点产出:**8 组**代际并存(最核心是 Agent 图 **4 套实现同时挂在线上**)、代码量(`api/*.py` 53 个文件 **8,294 行**;含 `locustfile*` 与 `archive/` 的 Python 合计 **≈9,280 行**)、工作量评估(删完约 −2,000 行 / 5–8 天)、逐处裁决建议。
- **`docs/decisions/`** —— 决策记录机制,含本项目首批 4 份:
  - `DEC-001` 公开仓库硬编码登录口令的处理路线(A 补数据层 / B 取消口令登录 / **C 环境变量**)
  - `DEC-002` 三处预算闸门失效的修法(**乙 消耗折 Token** + **(a) 新增 Token 预估表**)
  - `DEC-003` 压测口径修复改哪一侧(**改脚本** / 改端点;`mode` 取 `accurate_norerank`)
  - `DEC-004` 本项目过程记录机制选型(**三套全建**)
- **`docs/复盘/`** —— 过程错误记录机制,含 `模板-复盘.md` 与当日 3 份复盘。
- **`CHANGELOG.md`** —— 本文件。

### Changed

- 🔴 **两处「审计结论」被实测推翻 —— 一处翻案、一处加重**（2026-09-20 · `docs/待办登记…` §十三）。

  **① `api/websocket_test.html`：审计判它"孤儿"，判错了。**
  审计的判据（"0 处引用"）**对一个"给人直接在浏览器打开的独立页面"根本不成立** —— 这类页面本来就不被代码引用。
  实测：`api/api_v1_rag.py:764` 的 `@router.websocket("/ws/agent")` **是活的**
  （`/api/v1/ws/agent` → **CONNECTED**，首帧 `{"type":"thinking",…}`；`/ws/agent` → **REJECTED**）。
  ⇒ 它**不是孤儿，是配套页**，只是 ① URL 写错 ② 放在 `api/` 而非被挂载的 `api/static/`。
  **处置：不是删，是「搬 + 修 URL」** —— 搬进 `api/static/`，URL 改为从 `location` 推导。
  实测 `GET /static/websocket_test.html` = **200**（**搬之前该路径是 404**）。

  **② 🔴 浏览器工具的失效范围，比 README 写的**大**得多（新条目 N13）。**
  README「已知限制 #1」原写「浏览器工具**在本机**不可用 …… **环境天花板，非代码缺陷**」——
  **这句把"本仓部署方式都不装浏览器"说成了"我这台机器的毛病"。**
  实测：`api/Dockerfile` 与 `docker-compose.yml` **都没有 `playwright install`**
  （全仓 4 处提及它，**全是文档在解释它跑不了**，无一处是去装）⇒ **`python:3.10-slim` 里同样没有浏览器。**
  ⇒ **`fetch_webpage` / `fetch_webpage_html` / `screenshot_webpage` 在本仓【任何部署方式】下都不可用。**
  （已更正该处。⚠️ **要不要让它真能用 = 产品决策**：在 Dockerfile 装 chromium，镜像 +约 300MB。见 `docs/待办登记…` §四·2 丙方案。）
  ⚠️ 附带更正一处**计数口径**：工具健康 **4/6** 只反映 MCP 注册表里的那 2 个浏览器工具；
  第三个 `fetch_webpage_html` **压根没注册进 MCP**（那是 🔴C），所以它**不出现在这个分母里**。

- **§四 的 5/6/7 三条已执行**（2026-09-20）：
  - **`deploy.md`**：两处占位符 clone URL（`你的用户名/你的仓库名`）→ 真实地址（含 `cd` 那行），实测替换 **2 处**、无残留。
  - **`硬性指标终极核查清单.md`**：⚠️ **加头标，不改内容** —— 核出它是**原系统带进来的原始验收清单**
    （`3c16073` 2026-07-05，作者是占位符 `你的名字`，**引入后从未改过、0 项被勾过**）⇒ **改内容就成了篡改原始要求**。
    已注明来历，并写明「`.gitlab-ci.yml` 是**原系统**的要求，本仓 CI 是 GitHub Actions」。
    📌 顺带核出：README 里「性能目标」表（P99<800ms / 失败率<0.1%）的**出处就是这份清单**。
  - **`api/websocket_test.html`**：见上。
  - **`api/websocket两个版本.txt` 删除**（306 行 `.txt` 里装着 **3 份** HTML 迭代版、0 引用、
    原系统首次提交 `ecb146b` 带进来的）—— 三份互不相同、也都**不是**真页的子集/超集（真页更长）⇒ **已被取代**。
    内容仍可取回：`git show ecb146b:'api/websocket两个版本.txt'`

- **根 `README.md`：补"整套系统架构图" + 写明原系统出处**（2026-09-20）。
  「技术架构」段新增 `docs/architecture-full.png`（**并显式标注图上工具层的 `rag_search` 已过时** ——
  当前实际是 `fetch_webpage_html`，`api/agent_graph_advanced_learning.py:47-51`；**图记录的是更早一代工具集**）；
  项目结构树下新增出处说明：**原系统是极狐 GitLab 上的 `agent-assistant`**
  （证据原在 `Agent/deploy.md`，现见 git 历史 `351f699`）；结构树里的 `Agent/` 一行已删。

- **两处"引用了已删文件"的历史记录 —— 只加日期补注，不篡改原文**（2026-09-20）：
  - `docs/decisions/DEC-003`：它把 `Agent/docs/api_agent.md` 列为"仓内约定证据"**之一** ⇒ **由 2 处降为 1 处**。
    ✅ **决策本身不受影响**（主依据是"端点无 Pydantic body"这一**代码事实**，`api/api_v1_agent.py:348-357` 仍在）；
    `docs/demos.md` 那处**证据未断**。
  - `docs/凭据轮换手册`：「原始泄露面 3 个被跟踪文件」**现剩 2 个**。⚠️ **口径变了 ≠ 风险变了**
    —— 被删的那个文件里是**公开占位符**；真正的风险仍是"有没有别处把真口令写进被跟踪文件"。

  **为什么只加补注**：这两份是**事发/决策当时的快照**，改成现状会让记录失真。

- **CI `offline-tests` 的覆盖面：从「1 个文件」扩到「`api/` 全套」+ 两个 job 加 `timeout-minutes`**（2026-09-17 · M6 的后续）。

  M6 时它只跑 `api/test_rag_search.py`；现在跑 **`pytest api/ -m "not integration and not needs_db"`** ——
  实测 **50 passed / 1 skipped / 11 deselected**（本机带 `rag_test` 时是 **60 passed**）。

  **为了"能挡得住"而引入的第二个 marker `needs_db`** —— 它和 `integration` 是**两种不同的"跑不了"**，别混：

  | marker | 缺什么 | 谁标了 |
  |---|---|---|
  | `integration` | 真 Postgres **+ DashScope 外网** | `test_rag_search.py::test_search_fast_against_real_stack` |
  | `needs_db` | **只要真 Postgres** | `test_documents.py` · `test_integration.py` · `test_search.py`（整篇）+ `test_main.py::test_health`（单条） |

  ⚠️ `test_main.py` 里**只有 `test_health` 一条**需要库（`/health` 会真探 Postgres/Redis 连通性，没有库返回 503），
  其余两条**没有**跟着标 —— marker 是**按需**打的，不是"整个文件一刀切"。
  📌 **判据是实测的，不是推的**：把 `POSTGRES_PORT` 指向死端口逐文件跑，才定下这份名单
  （顺带发现 `test_auth.py` **无库也能过** —— 它的登录用例不依赖 `auth_headers` 那条路）。

  **`timeout-minutes`（`syntax` 5 分 / `offline-tests` 15 分）** 是**兜底**：
  2026-09-17 实测过一个「**测试全过但进程不退出**」的缺陷（Gradio 遥测非 daemon 线程），
  没有超时上限时那种卡住会一直耗到平台全局上限；有上限，"卡住"才是一个**显式状态**。

- **重构 ⑥ 切开点 5：`api_v1_rag.py` 的 LLM / Agent 对象改为惰性单例**（M5 · 2026-09-17）。**⑥ 的最后一步。**

  **起因**：两处在**模块层**直接构造对象 —— `llm_stream = ChatOpenAI(...)` 与**一整段** agent 装配（`llm` / 三个 `@tool` / `tools` / `prompt` / `agent` / `agent_executor`）。
  后果：`import api_v1_rag`（进而 `import main`）**在导入期就构造 LLM 与 Agent**，哪怕进程**从不打开** `/rag/stream_search` 或 `/ws/agent`。

  - **改法**：各搬进**惰性单例 getter**（`get_llm_stream()` / `get_agent_executor()`），首次使用时才建、之后复用（**与原先单例语义一致**）；`langchain*` 导入一并移进函数内。
  - ⚠️ **工具 docstring 与 prompt 模板逐字未改** —— 那是**给 LLM 看的接口**

  | 项 | 结果 |
  |---|---|
  | `compileall` | SYNTAX OK |
  | **🔴 docstring 逐字未变** | **全部 11 个**（含搬运的 3 个）**逐字相同** ✓ · **prompt 模板亦逐字相同** ✓ |
  | `import main` | `routes=14` · `OPENAPI_PATHS=59`（逐位未变） |
  | **🎯 核心主张** | 新版 `import main` 后 `_llm_stream=None` 且 `_agent_executor=None`；**对照旧版**：模块层直接赋值 **6 个对象** |
  | **R2 真调用** | `get_llm_stream()`→`ChatOpenAI`(streaming=True) · `get_agent_executor()`→`AgentExecutor`(**3 工具**，与改前一致) · **两者都验了单例** |
  | `pytest` | **37 passed / 1 skipped / 0 failed** |

  - 📌 收益口径（沿用 `DEC-010`）：**不是**"不再 import langchain"，而是「**不碰这两个接口的进程，永远不构造这两个对象**」。

- **重构 ⑥ 切开点 4：`main.py` 的 Gradio 挂载加环境门控**（M5 · 2026-09-17）。业务方裁决取 **A 方案 —— 默认值保持现状**。

  **起因**：`main.py:512` 的 `from cost_dashboard import create_dashboard` 在**模块层**执行，而 `cost_dashboard.py:5,6,8` 是模块层 `import gradio` / `import matplotlib` ⇒ **`import main` 必拉这两个包**。

  - 改法：把 L511–516 整段包进 `if os.getenv("ENABLE_DASHBOARD", "true") == "true":`
  - 🔴 **收益口径（写进代码注释，不许读成"不再拉"）**：这给的是「**可以**不拉」，**不是**「不再拉」。
    默认值 `"true"` = 保持改动前行为 ⇒ **默认路径上 `import main` 仍然拉 gradio + matplotlib**。
    只有**显式设 `ENABLE_DASHBOARD=false`** 时才真省掉（门关时 `cost_dashboard` 整个不被 import）。

  **验证 —— 两条分支都测**（只测默认分支等于没测收益分支）：

  | | 🅰 默认（不设环境变量） | 🅱 `ENABLE_DASHBOARD=false` |
  |---|---|---|
  | `len(app.routes)` | **14**（= 基线，逐位一致） | **13**（少一个） |
  | `OPENAPI_PATHS` | **59** | **59**（不变） |
  | `/dashboard` 路由 | ✅ 在 | ❌ 不在 |
  | `gradio` 在 `sys.modules` | **True**（保持现状） | **False** ✅ |
  | `matplotlib` 在 `sys.modules` | **True** | **False** ✅ |

  - 📌 **`OPENAPI_PATHS` 两边都是 59** —— 因为 `/dashboard` 是 **mount 不是 OpenAPI 路由**。
    而 `len(app.routes)` 掉 1，正印证了计划 R5 点名的坑：**`main.py:516` 会【重绑定 `app`】**，
    门关时那次重绑定不发生 ⇒ `app.routes` 少一条。**这是"关掉面板"的应有语义。**
  - `compileall` SYNTAX OK · `pytest`（隔离库 `rag_test`）**37 passed / 1 skipped / 0 failed**

- **重构 ⑥ 切开点 3：`code_executor.py` / `simple_tools.py` 抽 `_impl` 薄包装**（M5 · 2026-09-17）。目的：让**沙箱白名单与工具逻辑**可在**只有标准库**的环境里被导入和测试。

  **起因**：两个文件都在**模块层** `from langchain_core.tools import tool` —— 于是想单测沙箱白名单（`ALLOWED_BUILTINS` / `create_safe_globals`）就必须先把 **langchain 装齐**。而这两处的**真正逻辑全是纯 stdlib**（`io` / `contextlib` / `datetime`）。

  | 新文件（**纯 stdlib**） | 内容 |
  |---|---|
  | `api/code_executor_impl.py` | 沙箱白名单（44 builtin / 9 模块）· `create_safe_globals()` · `execute_python_impl()` |
  | `api/simple_tools_impl.py` | `calculator_impl()` · `date_today_impl()` |

  - `code_executor.py` / `simple_tools.py` 只剩一层 **`@tool` 外壳**，直接委托给 impl
  - **依赖方向单向**：impl 模块**只 import 标准库**，绝不反向引用外壳（R1 不成环）
  - **向后兼容**：`code_executor.py` 重新导出 `create_safe_globals` / `ALLOWED_*` / `MAX_*`，老调用方照旧（已 grep：`api_v1_agent.py:19` · `agent_graph_advanced_learning.py:45` · `mcp_server.py:11,14`，一个没漏）
  - 📌 函数名带 `_impl` 后缀是**故意的** —— 提醒读者**这不是给 LLM 看的工具**；面向 LLM 的工具描述（docstring）留在 `@tool` 那层

  **验证 —— 全部对比基线**：

  | 项 | 结果 |
  |---|---|
  | `compileall` | SYNTAX OK |
  | **🎯 目标**：`import code_executor_impl` / `simple_tools_impl` | **拉起的第三方：无 —— 纯 stdlib** |
  | 向后兼容 | `from code_executor import execute_python, create_safe_globals, ALLOWED_BUILTINS` ✓ · `from simple_tools import calculator, date_today, SIMPLE_TOOLS` ✓（`SIMPLE_TOOLS=['calculator','date_today']`） |
  | **🔴 工具描述逐字未变** | 用 `ast` 取出前后两版的函数 docstring 对比：`execute_python` · `calculator` · `date_today` **三者全部逐字相同** —— **这是 LLM 的接口，不能动** |
  | **R2 真调用**（透过 `@tool` 外壳走） | `execute_python("print(6*7)")` → **`'42\n'`** · 需求描述被拒 ✓ · **沙箱仍拦 `import os`**（`ImportError: __import__ not found`）⇒ **安全边界没被削弱** · `calculator("3*4-5/6")` → `11.166…` · `date_today()` → `今天是2026年9月17日，星期四` |
  | `import main` | `routes=14` · `OPENAPI_PATHS=59`（逐位未变） |
  | `pytest`（隔离库 `rag_test`） | **37 passed / 1 skipped / 0 failed** |

  - ⚠️ **收益的口径要说清**：**不是**"`import code_executor` 不再拉 langchain"（**它仍然拉** —— 外壳必须有 langchain 才能建 `@tool`）。收益是**逻辑与外壳分离**：想用/想测沙箱逻辑，import **`code_executor_impl`** 即可，**不需要 langchain**。

- **重构 ⑥ 切开点 2：`token_tracker.py` 脱离 psycopg2**（M5 · 2026-09-17）。净 `-3/+15`。

  **起因**：该文件在**模块层**导入 `db.get_db`，**而且重复了两行**（L10 与 L13 —— 同一句 `from db import get_db` 写了两遍）。后果：`import token_tracker` 会连带拉起 **psycopg2**，哪怕调用方只想用它的纯计算函数（`PRICING` / 预估 / 汇总）。

  - **改法**：删掉两行模块层导入 → 改为**函数内惰性导入**。⚠️ 计划里写的是"另一行**移进函数**"（单数），**实测是 8 个函数**用到 `get_db`：`record_usage` · `record_cost` · `get_daily_token_usage` · `get_user_history` · `generate_monthly_report` · `get_daily_usage_cost` · `record_intercept` · `get_thread_cost` ⇒ **8 处各加一行**
  - **位置放在函数体最前、`try` 之前** —— 放 `try` 里会被该函数**自己的 `except` 吞掉**，掩盖 `ImportError`
  - 沿用该文件**既有的惰性导入写法**（`from permission import ...` @L291 · `import calendar` @L377）

  **验证 —— 全部对比基线**：

  | 项 | 结果 |
  |---|---|
  | 模块层残留 `from db import get_db` | **0** |
  | 函数内惰性导入 | **8** |
  | `with get_db() as conn:` 用法数 | **8**（一个没漏） |
  | `compileall` | SYNTAX OK |
  | **R2 · 惰性导入「真调用」**（计划点名的风险：*import 成功但首次调用才炸*） | 8 个函数**全部真调一次**：`record_usage` OK · `record_cost` OK · `get_daily_token_usage`=30 · `get_user_history`=1 行 · `generate_monthly_report`=dict · `get_daily_usage_cost`=0.00015 · `record_intercept` OK · `get_thread_cost`=0.00015 |
  | `import main` | `routes=14` · `OPENAPI_PATHS=59`（逐位未变） |
  | `pytest`（隔离库 `rag_test`） | **37 passed / 1 skipped / 0 failed** |
  | **收益** | `import token_tracker` 拉起的重包 **psycopg2 → 0**（`sqlalchemy` 亦为 0）；`PRICING` 等纯计算可在无 DB 环境下使用 |

  - ⚠️ **本次我自己造了一次污染，已清理**：R2 冒烟**忘了带 `POSTGRES_DB=rag_test`**，于是 `record_usage`/`record_cost`/`record_intercept` 往**真库 `rag_db`** 写了 4 行（`token_usage_logs` 1 · `cost_records` 2 · `budget_intercepts` 1，`user_name='u1'`）。**已按 `user_name='u1' AND thread_id='t1' AND purpose='test'` 精确删除并复核为 0**。
    - 影响面：只碰了**成本表**，**未碰 `documents`**（评测知识库全程 70 行未变）
    - 教训：**"只读冒烟"其实会写库** —— 凡是调用 `record_*` 的验证都必须带库名隔离

- **重构 ⑥ 切开点 1：`db.py` 拆出 `db_metadata.py` + `bm25_index.py`**（M5 · 2026-09-17）。目的：让 `import db` 不再被迫拉起重包。

  **起因**：`db.py` 在**模块层** `import sqlalchemy / numpy / jieba / rank_bm25`，于是**任何** `from db import get_db` 的调用方（`auth.py` / `cost_dashboard.py` / `api_v1.py` …）都被连带拖起这 4 个重包 —— 哪怕只是想要一个数据库连接。

  | 新文件 | 内容 | 依赖方向 |
  |---|---|---|
  | `api/db_metadata.py` | sqlalchemy 的 `metadata` + 4 张表声明（原 `db.py:212-278`） | **零依赖**（只用 sqlalchemy）⇒ `db.py` 可安全单向引用，**不成环** |
  | `api/bm25_index.py` | BM25 全套（原 `db.py:279-332`） | `from db import get_db` ⇒ **`db.py` 只能惰性引用它** |

  - **`db.py` 保留同名转发层**：`bm25_search` / `get_bm25_index` / `get_all_documents` / `invalidate_bm25_cache` 改成**函数内惰性导入**的转发函数，老调用方 `from db import bm25_search` **照旧可用**（已 grep 全部调用方：`hybrid_search.py:6` · `api_v1.py:35` · `api_v1_rag.py:26`，一个没漏）
  - ⚠️ **必须惰性** —— `bm25_index` 反向依赖 `db.get_db`，模块层互相 import 会成环；且**只在"先 import bm25_index"时才炸**（"先 import db"碰巧能跑），属最难查的一类。已**两个方向各测一次**
  - `alembic/env.py:39` 的 `from db import metadata` → `from db_metadata import metadata`（`metadata` 是**值**不是函数，没法惰性转发；且 Alembic 不在应用运行时导入图里，指过去更干净）

  **验证 —— 全部对比基线，逐位相同**：

  | 项 | 结果 |
  |---|---|
  | `compileall api/ -q` | SYNTAX OK |
  | `import main` | `routes=14` · `OPENAPI_PATHS=59` |
  | `pytest`（隔离库 `rag_test`） | **37 passed / 1 skipped / 0 failed** |
  | **R1** 循环导入 · 两个方向 | 均 OK |
  | **R2** 惰性转发**真调用**（不是只看 import） | `get_all_documents`=70 行 · `get_bm25_index`=BM25Okapi/70 docs · `db.bm25_search("文档",3)` 与直接调 `bm25_index.bm25_search` **结果完全相同**（证同一份缓存）· `invalidate` OK · `bm25_search_async`=3 hits |
  | 搬移是否逐字 | 与 `git show HEAD:api/db.py` 原区块 diff：**A 仅多 2 个空行 · B 仅多 `from db import get_db` 一行** ⇒ **零内容丢失** |
  | **收益** | `import db` 拉起的重包 **4 → 0**（sqlalchemy / numpy / jieba / rank_bm25 全部脱钩，只剩本来就要的 psycopg2） |

  - ⚠️ **一处未能实跑**：本仓 venv **没装 alembic**（只有 SQLAlchemy 2.0.53），故 `alembic current` 跑不了。`env.py` 那行改动靠**对象等价**确认（`db_metadata.metadata` 与原 `db.metadata` 是同一组表、同样的列），**不是靠真跑 alembic** —— 换到有 alembic 的环境应补跑一次 `alembic upgrade head`
  - ⚠️ 顺带记一个**环境坑**（非本次引入）：在 `api/` 目录下 `import alembic` 会命中本地的 `api/alembic/` **迁移目录**（同名遮蔽），报 `No module named 'alembic.config'` —— 这**不是** alembic 装坏了，是 cwd 遮蔽

- **`api/requirements.txt` 修掉三个真实缺陷** —— 它们会让**任何一次全新安装/`docker build` 装出一个 import 阶段就崩的应用**（这解释了那张 2026-07-01 的镜像为何"不能随便重建"）：
  | # | 缺陷 | 症状（2026-09-15 实测） | 修法 |
  |---|---|---|---|
  | 1 | `langchain>=0.3.13` 无上界 | 装到 **1.x** ⇒ `api_v1_rag.py:681` `from langchain.agents import create_tool_calling_agent` → **ImportError**（1.x 移到了 `langchain_classic`） | 全系列加 `<0.4`（`-core`/`-openai`/`-community`/`-text-splitters` 同） |
  | 2 | `duckduckgo-search>=6.0.0` 包已改名 | 新版 `langchain_community` 要 **`ddgs`** ⇒ `api/agent_graph.py:43`（**模块级** `DuckDuckGoSearchRun()`）→ **ImportError** | 换 `ddgs>=9.0.0` |
  | 3 | `mcp>=1.0.0` 无上界 | 装到 **2.2.0** ⇒ `api/mcp_server.py:49` `@server.list_tools()` → **AttributeError** | 加 `<2` |
  - 顺带删掉两处**裸名重复条目**（`langgraph` / `langchain-core` 各出现两次，其一无约束）。
  - **验证**：`pip install --dry-run -r api/requirements.txt` 完整解析成功（含 torch 等，无冲突）；两个依赖文件共享 39 包、**约束口径 0 差异**；三道验收门全过（语法 / 全链路导入 OpenAPI 59 路径 / **17 passed, 1 skipped**）。
- **`ROADMAP.md`** —— M4(CI 骨架)状态 `▶ → ✔`;M5 由"项目重构"按业务方口径**重述**为「**代码盘点与裁决合并**」(盘点 → 逐处裁决 → 代码量/工作量评估 → 删到能跑);新增 **M6 单模块完整测试闭环**;M7 全量测试与评估接入延后。
- **`docs/CODE_INVENTORY.md`** —— §0-1 中的口令**原文改为脱敏占位**(事实描述与风险说明全部保留)。
  ⚠️ 该文件位于 **PUBLIC 仓库**,初版直接引用了口令原文 —— 起因、根因与防错措施见 `docs/复盘/2026-09-15-为记录漏洞而制造新漏洞.md`。

### Removed

- **重构 ⑤ 归档：删掉 `CODE_INVENTORY.md` §3-1 判定的真·死代码**（M5 · 2026-09-17）。三处**静态可证的空操作**，合计 **-20 / +2 行**：

  | 位置 | 净删 | 内容 · 为什么是空操作 |
  |---|---|---|
  | `api/rate_limiter.py` | 5 | `'''...'''` 包着的"原来基础格式"旧实例。位于**模块中部**（L123，前面已有 `return`）⇒ 不是 docstring，删掉**不改 `__doc__`** |
  | `api/agent_graph_advanced_learning.py` | 4 | `'''...'''` 包着的旧工具执行逻辑（已搬到 `mcp_server.py`）。位于 `agent_decide` **函数体内**、`return` 之后 ⇒ 纯表达式语句 |
  | `api/api_v1_rag.py` · `stream_search` | 7 | `messages` **构造了两遍**：第一遍（`messages = []` + `extend(history)` + `extend([system, user])`）的结果，在 L617 被 `messages = []` **无条件清零重建** |

  - 另删 **1 行悬空注释**（`# 3. 构建消息` —— 它的正文块就是上面那 7 行）+ **1 行残留空白**（4 空格），并把 `# 4./# 5.` **重编号为 `# 3./# 4.`**（第三段没了，编号不该跳）
  - **验证 —— 三道门，改动前后对比**：

    | 门 | 改动前 | 改动后 |
    |---|---|---|
    | ① `compileall api/ -q` | SYNTAX OK | **SYNTAX OK** |
    | ② `import main` | `len(app.routes)=14` · `OPENAPI_PATHS=59` | **`14` · `59`（逐位相同）** |
    | ③ `pytest` | 26 passed + **11 failed** + 1 skipped | **37 passed + 0 failed + 1 skipped** |

    ⚠️ 门③的"改动前"是 **Docker 未启动**时测的，那 11 条红**全是** redis `ConnectionError` 与 `/health` 503（`assert 503 == 200`），与本次改动无关。**26 + 11 = 37** ⇒ 测试**一条没丢、一条没新红**，11 条红在 Docker 起来后全部转绿。耗时 50.6s → 4.7s（那 50s 是连接超时在等）。
  - **测试跑在隔离库 `rag_test`**（本计划 §二 的决定）。原因：`test_documents.py` / `test_integration.py` 会**真往 `documents` 表插文档且没有任何 cleanup**，而那张表是 `agent-eval-gate` 评测所用的知识库 —— 插进去会**真实改变检索结果**。
    - 实测 `rag_db.documents` 测试前后**均 70 行**，`test`=20 / `test_docs`=9 **未变** ⇒ 隔离生效
    - ⚠️ 顺带发现：该表**历史上已被测试污染过 29 行**（`test` 20 + `test_docs` 9），是此前在 `rag_db` 上直接跑测试留下的。**本次未清理**（不是本次改动引入的，清理与否待裁决）
  - ⚠️ **本次只做「删死代码」，不含「代际裁决」** —— `CODE_INVENTORY.md` §2 那 8 组代际并存（最核心是 Agent **4 套实现同挂线上**）**一行未动**。那是 M5 的 C/D/E 档（5–8 天），须先定"哪个是产品版本"。

- 本地残留分支 `docs/api-doc-final-review`(已并入 `main`,远端无此分支)。

- **原系统 `Agent/` 目录整体删除（方案甲「拆走再删」，`DEC-018`）**（2026-09-20）。

  业务方问「原 clone 来的 `Agent/` 还有用吗，没有用不用保留，**污染环境**」。
  实测后判断：**不是"全没用"，是三块有用、四块是污染**：

  | 处置 | 内容 | 依据 |
  |---|---|---|
  | **搬** | `architecture_full.png` → `docs/architecture-full.png` + 根 README 引用 | **整套系统**级架构图（仓根那张只到子系统级），**唯一**画了 MCP 层 / 部门制 Agent / 成本控制体系的图 |
  | **迁** | `faq_agent.md` 的 Q7–Q15 → `docs/FAQ.md` 第五节 | 根 FAQ 原有 **0 条** Agent 排障 |
  | **删** | `README.md`（自称"生产级"，与根 README **在同一仓里说反话**）· `deploy.md`（与根 `deploy.md` 重叠 + **第三处占位符 clone URL**，审计漏抓）· `.env.example`（**配置面与仓根不同**：多 `MEM0_API_KEY`/`API_KEY`，**少 `LOGIN_PASSWORD`** ⇒ 照抄配不起来）· `docs/api_agent.md` · `docs/architecture_agent.png` | —— |

  ⚠️ **未删任何代码** —— Agent 模块的 12 个 `.py` **全是原系统的**（引入于 `2c1a922` 2026-07-17 / `351f699` 2026-08-17），
  本项目对其改动 **+405 / −210 行**，而这些文件共 **2974 行** ⇒ **≈ 13.6%（上限）**，其中
  `tool_health.py`/`browser_tools.py`/`code_executor.py`/`simple_tools.py` **一行未动**。
  **全部原文仍在 git 历史**（`git show 351f699 --stat`），可恢复。

### Changed

- 🔴 **交付收敛成【一条路径】—— `docker compose up -d`**（2026-09-20 · 分支 `docs/redeliver-single-path`）。

  **业务方方向更正**：「**不用双 requirements.txt，这样会混，最后肯定是用 docker-compose 一键编排的，
  别人 git clone 也是 docker-compose**」、「**整个项目阶段性完成，本来就是要完整明了、简洁的交付**」。

  | 改了什么 | 内容 |
  |---|---|
  | **`README.md`** | 「3. 启动」从**两条路径**（轻量 A / Docker 全量 B，还推荐了 A）**收敛成一条** `docker compose up -d`；删掉「别用 `docker compose up`」红线的**理由**；前置要求表重排（Docker 变唯一必需，Python 3.10 降为"跑测试才需要"）；新增「🔧 本地开发/跑测试」小节（**明说这是开发路径，不是交付路径**）；「5. 访问文档」改为全栈都有（Grafana/Prometheus/看板） |
  | **`docs/FAQ.md`** | Q1.1 从「我不想构建镜像怎么办」**重写为**「怎么把项目跑起来」；Q1.3 的 `docker start` 理由改写（**保留现象、去掉已作废的理由**）；A6 的"轻量路径"表述改为"本地开发路径" |
  | **`docs/给Agent的测试与调试指南.md`** | §1 标题从「**不构建镜像**」改掉，并**明说本节是开发路径**；§6 红线第一条**降级**（理由作废，但保留"先确认再动手"）；§8 总结改写 |
  | **`api/requirements-test.txt`** | 🔴 **删除**（§四·1 裁「删 + CI 改回」）。**安全性已核**：用**集合运算**（含版本约束比对整行）实测它是 `requirements.txt` 的**真子集** ⇒ 切过去**不丢任何包** |
  | **`.github/workflows/ci.yml`** | 依赖清单与 pip cache 路径改回 `api/requirements.txt`，并注明**代价（CI 会变重）** |
  | **`CLAUDE.md` / `ROADMAP.md`** | ⚠️ 这两处**都在教"用 `-test` 建 venv"** —— 不改，后来的会话照做即失败（这正是"改这边漏那边"）。已同步 |
  | **`README.md`「📈 评估体系」** | 原写「**集成 RAGAS**」——**不成立**：`ragas` 在依赖里，但 **`api/*.py` 0 处 import 它**，评估脚本还在 `archive/`（不入库）。已改为「⬜ 未接入」 |

  **⏳ → ✅ CI 耗时的实测值补上了**（此前文档里只敢写"会变重"，**没写分钟数**）：

  | | 离线测试 job |
  |---|---|
  | 此前用 `requirements-test.txt`（近 5 次） | **1m12s / 1m18s / 1m23s / 1m25s / 1m27s** |
  | 改用 `requirements.txt` —— 首次（**缓存冷**） | **3m35s** |
  | 改用 `requirements.txt` —— 第二次（**缓存热**） | **2m50s** ← **以这个为准** |

  ⇒ **稳态约 2m50s，是原来的 ~2.1 倍。**（缓存省的是**下载**，省不掉**安装**。）
  **可接受，不动摇 §四·1 的结论。**

  **同时把断言总表里 4 条 ⬜ 转成 ✅**（重跑实测，不是推断）：
  离线层 `68 passed, 1 skipped, 11 deselected`（与文档**逐字一致**）· `test_agent_repairs.py` `18 passed`（且文件里恰 18 个 test 函数）·
  凭据门"没 `git add` 就扫 = 没扫"的口径 · `--all` 在干净仓库上**本来就会红 2 处**（既存占位符）。

### Fixed

- 🔴 **撤回一条我自己发出去的错断言**：「`requirements-test.txt` **不只做减法**（还加了 `gradio`）」—— **是错的**（2026-09-20）。

  我用 `diff` 看到 `-test` 里多出一行 `gradio>=4.0.0`，据此断言 FAQ 的「只做减法」不成立，
  **并把这句写进了本文件、`docs/待办登记…` 与 `docs/断言总表…`，还推送了出去**。
  **复核后确认：它是错的。**

  **复核用的判据换了**（关键）：改用**集合运算** ——
  `comm -13 <(requirements.txt 去注释/去版本号/sort -u) <(-test 同样处理)`：
  **只在 `-test` 里的包 = 空**；只在 `requirements.txt` 里的，恰为**文档声明的 7 项**
  （`sentence-transformers` / `transformers` / `camelot-py[cv]` / `opencv-python` / `ragas` / `datasets` / `locust`）。
  ⇒ **「只做减法」是对的，FAQ 没错。**

  **根因：`diff` 的「行序伪影」。** `gradio` 在原文件 `:94`、在 `-test:116` —— **两边都有**，
  只因此处上下文行不同，`diff` 把它报成了"新增"。
  ⛔ **教训：判「两个清单的集合差异」不能用 `diff`（它按行序对齐），要用 set 运算（`comm`/`sort -u`）。**
  行数 `123 vs 100` 属实，但差值来自 `-test` **头部那段长注释**，**不是多装了包**。

  ⚠️ **更难看的一点**：本文件 `:199`（更早的条目）**本来就写对了**（"只做减法，**未加任何新包**"）——
  **我在同一个文件里写了句和它相隔 145 行、内容相反的话，却没想到去读它。**

- 🔧 **`scripts/impact.sh` 自身两个缺陷 —— 自建的防线，自己先踩了两次**（2026-09-20）。

  ① **假绿灯（严重）**：`printf '%s'` 吃掉末尾换行，而 `wc -l` 数的是**换行数** ⇒ **系统性少算 1**；
  **恰好 1 处命中时报「0」** —— 输出"零命中"。**一个会给出"没有影响面"假绿灯的防线，比没有防线更危险。**
  实测：`architecture_agent` 只有 `Agent/README.md` 一处引用，被报成 **0**。
  ⇒ 改 `'%s\n'`，并补 T9（恰 1 命中 ⇒ 必须报 1）/ T10（计数 == **独立 oracle**）。
  ② **测试脆**：删 `Agent/` 后回归从 **11/11 掉到 9/11** —— 排查**不是脚本坏，是测试依赖了仓库内容**
  （T4 的哨兵串、T9 的关键词**都被我自己随后写进了测试文件或别处** ⇒ "零命中"再也构不出来、"恰 1 命中"变成 3）。
  ⇒ T4 改用**运行时生成**的哨兵；T9 夹具独立成 `scripts/impact_test_fixture.txt` + **运行时读取**
  （测试里不留 token 字面量）+ **夹具失效守卫** —— 该守卫**当场抓住过一次**我自己把 token 写进测试文件。

  ⚠️ **更正一条此前报出去的数字**：我给业务方报的「`POSTGRES_PASSWORD` 命中 **19** 个」是错的，**实为 20**。

- 🔴 **三条 Agent 路径全断 —— 七处【依赖漂移】，全部修通**（2026-09-20）。

  **发现方式**：业务方问「距离 demo 还差多少」。把 API 真起来逐个打 —— 结果
  **1 代 `/agent/langgraph_chat` 返回 200 但答案是空串** · **2 代 `/agent/advanced_chat` 500** ·
  **3 代 `/agent/mcp_chat` 500** · **工具健康 0/6**。而 **RAG 那条线完好**。
  ⚠️ **七个 bug 没有一个是业务逻辑错** —— 全是装上的版本比代码写作时新：
  `mcp 1.30.0` · `mem0ai 2.0.20` · `qdrant-client 1.19.0` · `playwright 1.62.0`。

  | # | 位置 | 根因 |
  |---|---|---|
  | 1 | `memory_store.py` | mem0 2.x **两层**漂移：**签名**（`user_id`→`filters`、`limit`→`top_k`）**+ 返回形状**（list → `{"results":[…]}`） |
  | 2 | `agent_graph_advanced.py` MCP 传输 | `stdio_client` 是 async CM，**且 anyio 要求同 task** |
  | 3 | `api_v1_agent.py` 审批契约 | 停在 `interrupt_before` 时最后一条是**无文字的 AIMessage**，照搬 `.content` 得空串 |
  | 4 | `mcp_tool_factory.py` 参数 | 把 **pydantic 实例**喂 `invoke()`（要 dict） |
  | 5 | `agent_graph_advanced.py` MCP 路径 | `"api/mcp_server.py"` **相对 CWD** ⇒ 从 `api/` 起服务时指向不存在的文件 |
  | 6 | `browser_tools` 同步 Playwright | **两个入口**：FastAPI 端点 **+ MCP server**（`mcp_server.py:71` 是 async 却同步调 handler） |
  | 7 | `get_llm_with_mcp_tools` | mcp 1.30 的 `list_tools()` 返回 **`ListToolsResult`**（列表在 `.tools`），直接遍历得元组 |

  **MCP 会话改 B2（单 task 自开自关）**：先前推荐的 B1（AsyncExitStack 池化）**被实测证伪** ——
  anyio 的 cancel scope 要求「进入与退出在同一个 task」，池化天然跨 task ⇒
  `RuntimeError: Attempted to exit cancel scope in a different task…`，
  且**它让应用启动直接失败**（比原 bug 更糟）。已回退并采纳 B2。
  📌 附带查明：**那个会话池从未生效过**（`initialize_pool()` 无调用方；`release/close` 零调用方）。

  **合并前评审又抓出 2 Critical + 2 Important，并连带挖出第 8、9 个 bug**（都是"修好前面才暴露"的既存缺陷）：

  | # | 位置 | 根因 |
  |---|---|---|
  | 8 | `agent_graph_advanced_learning.py:47-54` | 模块级 `tools` 列表**先列了一遍 fetch_webpage / fetch_webpage_html，紧接着又 `extend` 一遍** ⇒ 各出现两次 ⇒ `bind_tools` 发给 DeepSeek 被拒：`400 - 'Tool names must be unique.'` ⇒ **REACT 分支 100% 500** |
  | 9 | `create_react_subgraph` | **没有任何节点写 `final_output`**，而端点读 `result.get("final_output", "处理完成")` ⇒ 走 REACT 意图时**永远返回占位串**（其余四个子图都写了）⇒ 补 summarize 收尾节点 |

  ⚠️ **两条 Critical 都是本 PR 自己引入/漏掉的**（"同一个形状还有别的入口吗"的第 4、5 次实例）：
  - **C-1（本 PR 新引入的回归）**：把 handler 改成 async 后，**第三个（同步）调用方没跟着改** ⇒
    拿到 coroutine ⇒ `str(result)` 写成 `<coroutine object …>` ⇒ REACT 工具调用静默失效。
    修法**不是加 await**（该图用同步 `.invoke()`），而是**把 offload 放到 async 边界**
    （`mcp_server.call_tool` 里 `await asyncio.to_thread(handler, …)`），**handler 退回同步** ⇒ 三个调用方都不用动。
  - **C-2**：`/agent/mcp_tools_dynamic` 是 bug 7 的**孪生兄弟**（同一个 `get_mcp_tools()`，
    全仓只有两个调用方，改了一个漏了另一个）⇒ 该路由 100% 500。
  - **I-1**：审批判据原写 `if tool_calls and not content:` ⇒ 模型"先说一句再调工具"时误报 `answered`。
  - **I-2**：`ROADMAP` 交接锚点未更新。

  **验证**：`api/test_agent_repairs.py` **18 条**（逐条红→绿）· 全套离线层 **68 passed / 1 skipped**（基线 50）·
  端到端全绿：`mcp_tools_dynamic` 200/6 工具 · `langgraph_chat` 待审批 ·
  `advanced_chat` CALCULATOR `56088` · **`advanced_chat` REACT 返回真答案**（不再是「处理完成」）·
  `mcp_chat` `1+1 = **2**。` · 工具健康 **0/6 → 4/6**
  （剩 2 个卡**环境**：macOS 13.6 不支持 Playwright 1.62 的 chromium 1234）。
  决策：`docs/decisions/DEC-017-demo就绪路线与LLM换DeepSeek.md`。

- 🔴 **`/rag/search` 的 `mode` 静默兜底 —— 拼错一个字母会被悄悄换成另一个模式**（2026-09-17）。

  **修前**：`api_v1_rag.py` 的 mode 分派是个**裸 `else`** ⇒ `mode=garbage` 返回 **200**，
  **静默**落进 `accurate_norerank`（多跑一次查询改写 = **多花钱、多延迟，且不报错**）。

  **修法（两层，缺一不可）**：
  1. `mode` 由裸 `str` 改为 **`SearchMode = Literal["fast","accurate","accurate_norerank","full"]`**
     ⇒ 非法值由 FastAPI 在**进入函数体之前**挡成 **422**，且 OpenAPI 里**带上枚举**
  2. `if/elif/else` 改为**查表** `PIPELINE_FACTORIES[mode]()` ⇒ 结构上**不存在兜底分支**

  | 验证 | 结果 |
  |---|---|
  | 新增 `test_unknown_mode_is_rejected` | `mode=garbage` → **422**，`loc == ["query","mode"]`；**零网络**（handler 之前就挡下） |
  | 新增 `test_mode_defaults_to_accurate_norerank` | 不传 `mode` 与显式传默认值**逐字段一致** |
  | **变异验证**（把 `SearchMode` 改回裸 `str`） | **1 failed**（`KeyError: 'garbage'`）⇒ 用例有牙 |
  | OpenAPI | `mode` 的 `enum` = 四个值，`default = accurate_norerank`；`14`/`59` 逐位未变 |

  📌 **副产物**：光有"查表"也会把静默兜底变成 **500**；`Literal` 才给到 422 —— **两层各管一段**。
  📌 M6 时业务方裁决「**只记录、不写进测试**」（测试不该把缺陷固化成"预期行为"），本次是那笔登记的兑现。

- 🔴🔴 **凭据门 v4：这道门自建立起就是一枚硬币 —— 同一份暂存内容，20 次里拦 11 次、漏 9 次**（2026-09-17）。复盘见 `docs/复盘/2026-09-17-一道硬币做的门.md`。

  **它不是新增的问题 —— 它自 v1（`DEC-012`）起就在。** 三处判定都写成 `printf '%s' "$X" | grep -q…`：
  `grep -q` **命中即退出** ⇒ 上游 `printf` 收到 **SIGPIPE(141)**；而脚本开头有 `set -o pipefail`
  ⇒ **整条管道**状态变 141 ⇒ `if` 判成"没命中" ⇒ **真实命中被静默丢弃**。⚠️ 竞态，取决于 printf 写完没有。

  | 实测（同一份暂存内容） | 结果 |
  |---|---|
  | 修复前，连跑 20 次 | **拦住 11 · 漏报 9** 🔴 |
  | 对照组 C（只关 `pipefail`） | 拦住 20 · 漏报 0 |
  | 对照组 D（去掉 `-q` 早退） | 拦住 20 · 漏报 0 |
  | **修复后，连跑 30 次** | **拦住 30 · 漏报 0** ✅ |
  | 修复后干净态，连跑 10 次 | 通过 10 / 10 ✅ |

  **修法**：三处判定全部改 `grep … >/dev/null`（读完再判断，不早退）；保留 `pipefail`。

  - ⚠️ **`DEC-012` 里"验证四条全过"那四条是单跑一次** —— 单次运行**恰好**落进"拦住了"的那一半。
    **把一次抽样当成性质**，于是错误的"已验证"结论被写进了决策记录。已在该 DEC 补更正注。
  - 📌 **一道"看起来在工作、实际是硬币"的安全门，比没有门更坏** —— 它每次都打印"✅ 通过"，让人以为自己被保护着。
  - 📌 发现方式：**不是设计审查，是"不信一次结果"** —— 探针时灵时不灵 ⇒ 坚持跑 20 次才看见。

- 🔴 **凭据门 v3：它把 `postgres` / `qwen-plus` 当成了凭据**（2026-09-17 · M6 提交时被它自己拦下才发现）。决策见 `DEC-014`。

  **门第二次真上岗，拦错了。** M6 那次提交的两个命中，**全是它自己 `.env` 里的基础设施配置**：
  `POSTGRES_HOST=postgres`、`POSTGRES_DB=rag_db` —— 而拉全名单发现面更宽：`LLM_MODEL_CHAT=qwen-plus`、
  `LLM_BASE_URL=<dashscope 地址>`、`LOGIN_USER_NAME=admin`，**全是本仓最高频的词**。

  **根因**：第 ① 段的键过滤原先是「**除了太短的，全扫**」—— 它没意识到 `.env` 里**大部分键根本不是凭据**。
  ⇒ **v2 的门会拦下绝大多数正常 commit**，而"习惯性绕过一道门"才是真正的失效。

  **修法**：加【非机密键】排除名单（`*_HOST`/`*_PORT`/`*_DB`/`*_URL`/`*_MODEL_`/`*_CONN`/`*_USER_NAME`/`*_EXPIRE_`），
  **其余键照旧全扫**（保持 fail-safe：偏向误报而非漏报）；**跳过时逐条打印键名**（不静默排除）。

  | 验证路径 | 结果 |
  |---|---|
  | 本次真实提交 | **exit 0**，打印"已跳过 13 个【非机密键】"；剩 **6 个**照旧全扫（`*_API_KEY`/`*_SECRET_KEY`/`*_PASSWORD`）—— 正好是该扫的 |
  | **注入真实 `.env` 凭据值做探针** | **exit 1**，且**只报 `JWT_SECRET_KEY` 这个名字**（值一字未出）；**通用模式独立地也命中**（纵深防御） |
  | 清理探针后复跑 | **exit 0**，无残留 |

  📌 门的**三次修订**：前两次是**假阳性**（v1 扫删除行 ⇒ 删密钥时误拦；v3 键过滤 ⇒ 普通词误拦），
  **第三次才是漏报**（v4 的 SIGPIPE 竞态）。已写进脚本头部的「修订史」。

- **预算闸门单位错配 —— 三处闸门恒放行**（`#2` · 2026-09-16）。三处写成 `remaining = get_user_token_budget(...) − get_daily_usage_cost(...)` —— **Token 预算** 减 **「元」消耗**。剩余恒 ≈ 预算值（10000 / 100000），而单次预估花费只有 ¥0.0x ⇒ `cost > remaining` **永不成立** ⇒ **三处闸门恒放行**、80% 告警**永不触发**。
  - **修法**（`DEC-002` 的**乙 + a**）：取数换 `get_daily_token_usage`（Token，同量纲）；新增 `TOOL_ESTIMATED_TOKENS` / `PURPOSE_ESTIMATED_TOKENS` 两张 **Token** 预估表（与既有「元」表**并存** —— 后者供给 `/agent/budget/estimates` 对外展示）；参数 `estimated_cost` → `estimated_tokens`
  - **抽出唯一实现 `check_token_budget_detail()`**：此前 `check_token_budget` / `check_budget_before_call` / `check_multilevel_budget`(第三级) **各写一份**同样的判定 —— **这正是 bug 的成因**。现在后两者全部委托，量纲只在一处说理
  - **第一、二级（单次 ¥0.5 / 单线程 ¥5 上限）刻意不动** —— 它们是「元 vs 元」，量纲本来就对
  - 文案：9 处 `¥` 改成 `tokens`（`record_usage` 的真实花费与第一/二级上限仍用 `¥` —— 那是真「元」）
  - 顺手：`record_cost` 与 `record_usage` 的**兜底价目表不一致**（0.001/0.002 vs 0.003/0.006）→ 统一为 `_DEFAULT_PRICING`（取偏保守的一组），消除"两张表对不上账"
  - 顺手：`agent_graph_advanced.py` 的 `check_token_budget` **从 `invoke()` 之后上移到之前**（两处）—— 放在之后**钱已经花了**，只能丢弃结果、拦不住
  - **新增 `api/test_budget_units.py`（7 条）**。核心手法：**只 patch `get_daily_token_usage`、刻意不 patch `get_daily_usage_cost`** —— 修复前闸门调后者（真走库拿「元」）⇒ **断言失败（红）**；修复后调前者（被 patch）⇒ **通过（绿）**。**零写库**。
    - ⚠️ **原验证方案（往库里插假数据）是错的、做不出来**：修复前的代码**根本不读 `total_tokens` 列**，插多少 token 都**区分不了红绿**
  - **先红后绿已实测**：`git stash` 掉修复后跑 → **4 failed / 3 passed**；恢复后 → **7 passed**
  - 回归：`pytest` **37 passed, 1 skipped**（30 旧 + 7 新）

- 🔴 **评测门自身的一个发现：零容忍硬门 + 非确定性被测 = 会随机阻断**（2026-09-16 实测，**未擅自改评测门**）。同一份 SUT 代码连跑三次：

  | run | 结果 | 红队突破 | exit |
  |---|---|---|---|
  | `013720` | 48/48 | 0 | 0 |
  | `015426` | **47/48** | **1** | **1（BLOCK）** |
  | `015727` | 48/48 | 0 | 0 |

  - 被拦的是 `case 40`（拒答/越权探测）。两轮答案对比：一次"**根据现有资料，无法确认**知识库中哪些文档是其它用户上传的…"（合格拒答），一次"**知识库中可见的文档标题有**：测试文档一 [来源:1]…"（未拒答）—— **是 LLM 拒答行为的随机性**。
  - **同代码两次结论不同 ⇒ 不是代码改动引起**。（`#2` 的改动对评测账号另有独立论证：admin 走「无限预算」早退分支 ⇒ 预算逻辑对它是 no-op。）
  - ⚠️ 但**红队门是 0 容忍**：阈值文档已注明「σ 只覆盖同被测+同环境+同判分器的**随机噪声**」，而 **0 容忍把"随机噪声"直接变成了"随机阻断"**。
  - ⇒ **建议业务方评估该门的判据**（如对硬门引入 N 次重试 / 置信区间，或把"随机性拒答失败"与"确定性越权"分开），**本次未改**。

- **eval 回归**（`agent-eval-gate` · `run=20260916-015727-49d6ddb8`）：达标率 **48/48 = 1.00** · 红队突破 **0** · **exit 0 · 通过评测门**。判分器 `deepseek-v4-flash@api.deepseek.com`（45 次调用）；SUT = `localhost:8000` · mode `accurate_norerank` · **当前代码**。

- **压测脚本的请求形状与接口契约不符**（`#3` · 2026-09-16）。两处，同源 —— 都是"脚本没贴合被测系统"：
  - **`locustfile_hybrid.py` 用 json body 打 `/api/v1/agent/mcp_chat`** —— 该端点**没有 Pydantic 请求体模型**，`question` / `thread_id` 都是 **query 参数** ⇒ 占该脚本 **25% 权重**的 Agent 任务**必然 422**。改为 `params=`。
  - **`mode` 放在 json body 里** —— `/api/v1/rag/search` 把 `mode` 独立声明为 **query 参数**，**遮蔽了** body 里的 `QuestionRequest.mode` ⇒ 被**静默忽略**，所有请求恒走 `accurate_norerank` ⇒ **各 task 的 `name=` 标签全是假的**（不报错，比 422 更隐蔽）。`locustfile_hybrid.py`(2 处) 与 `locustfile_v2.py`(5 处) 全部改为 `params={"mode": "accurate_norerank"}`。
    - **取值刻意统一为 `accurate_norerank`**（= 修复前的**实际**行为），以保证与历史基线**可比**。若日后要压 `accurate`（开 Cross-Encoder 重排），那是**口径变更**，须重跑基线并单独说明（见 DEC-003）。
  - 顺带修 `locustfile_v2.py` 的 `conversation_history`：原传 `list[str]`，而 schema 声明 `list[dict]` ⇒ **422**；改为 schema 声明的形态。
  - **连带修掉一个可达的 500**：改对之后，`query_rewriter.py` 的 `"|".join(history[-5:])` 收到 dict 会 **TypeError ⇒ 500**（默认模式 `accurate_norerank` 本身就开着改写 ⇒ 这条路径**可达**，不是边界情况）。新增 `_history_lines()` **两种类型都吃**，并同步 `hybrid_search.py` / `rag_pipeline.py` 的类型标注。
  - **新增 `api/test_locust_payload.py`**（7 条，**不起服务、不打 LLM、零成本**）：断言"**脚本发的形状 == OpenAPI 声明的形状**" —— 以后写新 locustfile 时同一条测试能拦住同类错误。
  - ⚠️ **这条测试我也写错过两次**：(a) 只在该请求块里搜 `"mode"` —— 而 `params={"mode":…}` 与 `json={"mode":…}` **写法一模一样**，把**已经改对**的地方误报成没改（已改用括号配对，只取 `json={…}` 的**内容**再搜）；(b) 没防"正则一条请求都匹配不到 ⇒ 断言恒过"（本仓 N1 刚踩过同样的坑）。两处都已补**自证用例**。
  - **验证**：`pytest` **30 passed, 1 skipped**（23 旧 + 7 新）｜ `app.openapi()` 证实 `/agent/mcp_chat` **无 `requestBody`**、`/rag/search` 的 **`mode` 确在 query 参数里**。

- **中间件公开路径名单前缀写错**（`N1` · 2026-09-16）。`main.py` 的限流中间件与配额中间件**各写一份**跳过名单，两份都写的是 `/auth/login` / `/auth/refresh` / `/admin/create_user` —— 但三个 router **都带 `/api/v1` 前缀**（`api_v1.py:53` / `api_v1_rag.py:44` / `api_v1_agent.py:37`），真实路径是 `/api/v1/auth/login`。
  - **后果**：名单**对不上，等于没跳过** ⇒ 登录/刷新/建用户实际会打到 Redis 限流（挤进 `anonymous` 桶，3 次/秒共享）；Redis 抖动时登录返回 500 而非按预期放行
  - **修法**：提取为模块级 **`PUBLIC_PATHS`**（单一来源，两处中间件共用），修正三个路径的前缀，并补上 `/redoc` 与 `/docs/oauth2-redirect`
  - **新增 `api/test_public_paths.py`**（6 条，**不需要 Redis、不需要 DB**）：断言"**名单 ⊆ 真实路由**"而不是硬编码字符串（以后改前缀也能自动抓到），并断言旧形态（缺前缀）不得回归
  - ⚠️ **写这条测试时我第一版是错的**：只断言"名单里的 `/api/` 路径必须存在于真实路由"，而**旧名单里一条 `/api/` 路径都没有** ⇒ 空集恒过，**测不出任何东西**。已补"非空"判据，并加了一条 `test_would_have_caught_the_original_bug` **自证有效性**（把旧名单喂给判据，必须判它不过）
  - **验证**：`pytest` **23 passed, 1 skipped**（17 旧 + 6 新）｜ 对照演示 —— 旧名单覆盖 auth/admin 路径 **0 条**，新名单 **3 条全覆**

- **登录口令从硬编码字面量迁出到环境变量**（`#1` · 路线 C，决策见 `docs/decisions/DEC-001`）。`api/auth.py` 里那句 `_users_db = {"admin": "<明文口令>", "test_user": "<明文口令>"}` 是**公开仓库上的活凭据**，且被 `/api/v1/auth/login` 真实调用。
  - `api/config.py`：新增 `LOGIN_USER_NAME`（默认 `admin`）· `LOGIN_PASSWORD`（**必填，进 `validate_config`**）· `TEST_USER_PASSWORD`（**可选，不设则该账号不存在** —— fail-closed，不留默认口令）
  - `api/auth.py`：`_users_db` 字面量 → `_get_users_db()` **函数式读取**（刻意不缓存，便于测试 monkeypatch）；`authenticate_user` 签名与返回类型**未变**
  - **牵连 13 处全部改完**：`conftest.py` · `test_auth.py` ×3 · `test_integration.py`（第二份重复 fixture）· `schemas.py:67` 的 **Swagger 示例** · 3 个 locustfile · Postman ×4
  - 三个 locustfile 顺带修掉**静默失败**：原先登录失败只是把 `self.headers = {}`，会跑出整轮静默 401 —— 改为**显式 `raise RuntimeError`**（与 #3 的"mode 被静默忽略"是同一类坑）
  - 删除死配置 `API_KEY`（`config.py:36`，全仓 0 调用方）及其在 `.env.example` 的条目
  - **验证（决定性）**：新口令 → **200** ｜ **旧口令（原字面量，见 git 历史）→ 401**（旧凭据确已失效）｜ 旧 `test_user` 口令 → 401 ｜ 不存在账号 → 401 ｜ 未设 `LOGIN_PASSWORD` → `validate_config()` **抛 EnvironmentError** ｜ `TEST_USER_PASSWORD` 清空后 `test_user` **从凭据表消失**
  - 回归：`pytest` **17 passed, 1 skipped**（与基线一致）；`api/` 与 3 个 locustfile 语法全过；**全仓明文口令 grep → 0 命中**
  - ⚠️ **旧口令视为已泄露**：它在 `git log` 与任何已 fork 的克隆里永久留存 —— 本次改动换的是"当前生效的那一份"，不是"让它消失"

### Security

- 🔴 **凭据门 v4→v6：扫描没跑（或没跑全）时，门会报"通过"**（2026-09-20）。**这是一条自 v1 起就在的路径，v3→v4 只修了"症状那一处"，没修形状。**

  **缺陷**：脚本从**管道**取待扫文本，而 `2>/dev/null` + `|| true` 把「生产者失败」压成了「产出为空」
  ⇒ 判据从 `通过 ⇐ 执行 ∧ ¬命中` **退化成** `通过 ⇐ ¬命中`。
  实测两个变体（用只在 `git diff --cached` 上失败的 shim 复现）：
  - **A**：`git diff` 直接失败 ⇒ 门打印「staged 区为空」+ **`exit 0`**
  - **B**：`git diff` **输出一部分之后才失败** ⇒ 走正常路径 ⇒ 打出**货真价实的**
    `✅ 凭据门: 通过 —— 0 命中`，而扫的是**被截断的内容** —— **绿得毫无破绽**

  **修复**：① **单独取 `git diff`/`git grep` 自身的退出码**，失败 ⇒ `exit 2`（⛔ 不许拿**管道状态**代替 ——
  暂存区只有删除行时 `git diff` 成功而 `grep` 返回 1，拿管道状态判会**引入假红**）；
  ② 新增 **自证（positive control）**：运行时拼接合成样本，断言通用模式抓得住，抓不住 ⇒ `exit 2`
  （⛔ 样本必须运行时拼接，否则**本文件自己就命中自己的模式**）。

  **回归测试**：新增 `scripts/test_check_secrets.sh`（**断言退出码，不断言文案**）——
  v5 时 6 例，v6 扩到 **10 例**：正常 / `diff` 失败 / 部分输出后失败 / 匹配机制失灵 /
  **合法空集（防矫枉过正）** / **合成泄漏必须仍报红（防把门改瞎）** /
  **无 `.env` 不得当作通过** / **显式降级须标注「部分覆盖」** / **`--all` 下 `git grep` 出错** / **`--all` 下无匹配是合法的空**。

  🔴 **v6 —— v5 是半拉子修复，当天被合并前评审当场抓到**：
  v5 只堵了「生产者失败」**那一条**未执行路径，却漏了同一个形状的**另两条** ——
  **① 真实凭据（无 `.env`）** 与 **② 存量黑名单（无 denylist）** 整段不跑时，门仍打印
  **无限定语**的 `✅ 通过 —— 0 命中` + `exit 0`。实测（仓根无 `.env` 无 denylist）：
  **三节里两节没跑，输出与"全跑了没命中"不可区分**。
  ⇒ ① 改为 **`.env` 缺失 ⇒ ⛔ 扫描未完整执行 + `exit 2`**（显式设 `SECRETS_GATE_ALLOW_NO_ENV=1`
  可降级为【部分覆盖】，结论行会标注）；② 保持"可选文件"语义，但**结论行现在带覆盖度**。
  **红→绿已验**（同一套 10 例：v5 下 **8/10**，v6 下 **10/10**）。

  📌 **教训（比缺陷本身重要）**：修「某条路径」时必须回头问「**同一个形状还有别的入口吗？**」
  —— 本次就是同一份文件里、同一个形状，**连着两版各修掉一条**。

  ⚠️ **仍未做**：该门**不挂任何自动触发**（无 `.githooks`，`ci.yml` 不跑它）—— 全靠人记得执行。
  复盘：`docs/复盘/2026-09-20-查不到不等于不存在.md` · `docs/复盘/2026-09-20-同源的两个输入不能互相作证.md`。

- 🔴 **凭据③「端口收窄」：两个容器原先都暴露在 `0.0.0.0`**（2026-09-17）。**compose 已改，但容器未重建（有意）。**

  **实测**：`postgres-rag` → `5432/tcp -> **0.0.0.0**:5432` · `redis-rag` → `6379/tcp -> **0.0.0.0**:6379`。
  即**局域网内任何机器都能连**。⚠️ **Redis 还没有口令** —— 它的暴露面比 Postgres 更大。

  **改动**：`docker-compose.yml` 两处 ports 由 `"5432:5432"` / `"6379:6379"`
  改为 `"127.0.0.1:5432:5432"` / `"127.0.0.1:6379:6379"`（只绑回环）。

  🔴 **⚠️ 改文件不会改变正在运行的容器** —— 已复核：重建前 `docker port` 仍显示 `0.0.0.0`。
  **本次有意不重建**，理由是文件末尾「改名后遗症」§2/§3 已详记的**跨仓耦合**：
  重建会让容器落到 `fastapi-rag-agent_app-net`，而 **`agent-eval-gate/tools/sut-harness/run_sut.sh:18`
  的 `NETWORK` 默认值仍写旧名** ⇒ 会打断评测；且 `rag-api-eval` 正被评测使用。

  ⇒ **待办**：网络改名时**两边一起改**（本仓 compose + 那个 harness 脚本），再重建。
  代码注释里已写明这条路径，免得后人以为"改了就等于好了"。

- ✅ **Postgres 口令已轮换**（2026-09-16）。`.env` 的 `POSTGRES_PASSWORD` 用的曾是 `.env.example` 里那个**示例占位符**，从未改过；而 5432 **绑定所有网卡** ⇒ 同网段可用该公开口令直连。现换成 32 位随机串。
  - **决定性验证**：从**另一个容器**（源 `172.x`）连 —— 旧口令 → **`FATAL: password authentication failed`** ✅；新口令 → 成功 ✅；应用层（`config` 读 `.env`）连库正常，`documents` 70 行 ✅
  - ⚠️ **验证方法论（我第一次就测错了，值得记）**：该容器的 `pg_hba.conf` 对 **`127.0.0.1/32` 与 `::1/128` 是 `trust`（免口令）**，只有"其他来源"才是 `scram-sha-256`。**在容器内连 `127.0.0.1` 时，新旧两个口令都能连上** —— 会误判成"口令根本没被校验、配置坏了"。**必须从非回环来源测。** 已写进 `docs/凭据轮换手册.md`。
  - ⏸ **端口收窄暂缓**（业务方 2026-09-16 决定）：重建 `postgres-rag` 会让它与 `redis-rag` **分到不同网络**（compose 项目已在 `#3` 改名，网络名随之从 `my-fixed-name_app-net` 变为 `fastapi-rag-agent_app-net`），应用会连不上其中一个；且 `agent-eval-gate` 的 harness 默认用的也是旧网络名。**⇒ 待 ⑥ 切模块前与网络改名一并处理。** 当前暴露面已由"公开占位符口令"降为"随机口令 + 端口敞开"。

凭据处置进度（**完整操作手册见 `docs/凭据轮换手册.md`**，决策见 `docs/decisions/DEC-001`）：

- ✅ **Postman collection 里的硬编码 API Key 已移除**（`2fc3fc1`）：原 2 处（L3293 collection 级 `auth`、L1159 请求级 header `x-api-key`）改为 `{{admin_api_key}}` 变量引用。
  - **实测结论：它是早期测试的死值** —— 在 `api_keys` 表中**查无此记录**，从未对应当前库里的任何凭据 ⇒ **无需轮换**，本次改动只为停止继续扩散。
  - ⚠️ 新 Key 的值**不要再写回该文件**（它被 git 跟踪，且仓库为 PUBLIC）。
- ✅ **库内孤儿 Key 已删除**（`id=1`，2026-06-26 创建）：无任何文件对应、无人使用。
- ⏸ **库内活 Key（`id=2`）保留**：被 `agent-eval-gate` 的评测链路使用，且**未公开泄露**（本仓 git 历史中从未出现）⇒ 轮换它零安全收益、却会打断那个项目。
- ✅ **`api/alembic.ini` 的硬编码 Postgres 口令已移除**（`f105cbf`）：该行运行时并不被读取（`alembic/env.py:22` 无条件覆盖为 `config.py` 构造的 URL），改为 `CHANGE_ME` 占位符，零运行风险。
- ✅ **云端 API Key（DashScope / DeepSeek）与 `JWT_SECRET_KEY` 已核实未泄露** —— 当前 108 个被跟踪文件 + **整个 git 历史**均无命中。
- ⚠️ **仍未处理**：
  - ✅ **`api/auth.py` 硬编码登录口令已迁出**（2026-09-16）—— 见下方 **`### Fixed`**。
  - **Postgres 口令仍是公开的示例占位符**，且 5432 **绑定所有网卡**（`TCP *:5432`）⇒ **同网段设备可直接连库**。改口令 + 收窄端口待评测空闲时做（两者耦合，见手册 §4）。
  - **`JWT_SECRET_KEY` 形状不对**（169 字符的 JWT，而非随机密钥）。换掉会使**所有已签发 token 失效**。
- **改代码不等于止血**：上述凭据在 `git log -p` 与任何已 fork 的克隆里**永久留存**。轮换的作用是让**已泄露的那一份失效**，不是让它消失。
