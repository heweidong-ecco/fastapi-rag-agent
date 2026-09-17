# ROADMAP · fastapi-rag-agent 生产级 RAG + Agent API 服务

- 版本:0.2 · 日期:2026-09-15 · 图例:✔ 完成 · ▶ 进行中 · ⬜ 待办 · ⏸ 暂缓
- 依据:`CLAUDE.md`(架构与修复记录) + git log
- **本文件是给新会话的接续锚点** —— 换会话、换机器,从这里读起。

## 当前指针(每次 commit 前更新)

- 🔴 **最高优先级(2026-09-15 业务方批准)**:**`docs/重构计划-2026-09-15.md`** —— **开工前先读它**。
  - **其余 M5 裁决工作让位于它**
  - 含一条**前提级更正**:本机**能跑测试**(曾误判为"做不了运行期验证")。环境走 **本仓自建隔离 venv**(`venv/`,Python 3.10.10)+ **`api/requirements-test.txt`**(剔重版,**不含 torch 系**)
  - 借来的 `ai-learning/venv` **不可用** —— 它的 fastapi 0.115.11 与 starlette 1.6.0 不配对,任何 `APIRouter(...)` 都建不起来
  - ⇒ **"切模块"不再是测试的前置条件**
  - **执行顺序与旧计划相反**:基线 → 修 bug → 归档 → 切模块 → M6
  - 登记的另两处:`CLAUDE.md` 顶部(每会话自动加载,但不入库) · 该文件正文
- **四个 bug 已完成（2026-09-16）**:✅ #1 认证口令(PR #6) · ✅ N1 中间件路径(PR #7) · ✅ #3 压测口径(PR #8) · ✅ #2 预算单位(PR #10) —— 各一个 PR、独立可 revert
- **⑤ 归档(第一刀)✅ 完成(2026-09-17 · PR #13)**:删掉 `CODE_INVENTORY.md` §3-1 判定的 **16 行真·死代码**(另 1 行悬空注释 + 1 行残留空白;净 −20/+2 行)。三道门前后对比:`compileall` OK · **`OPENAPI_PATHS=59` 与 `len(app.routes)=14` 逐位未变** · pytest **37 passed / 0 failed**(改动前同环境 26 passed + 11 failed,11 条红全是 Docker 未启动的 redis 连接错,**26+11=37,一条没丢**)
  - ⚠️ **⑤ 只做了「删死代码」这一半** —— **「给被取代的代际原地加 `# STATUS: superseded → §2 组N` 标记」还没做**。原因:标记要**先判定"哪一代是产品版本"**,那正是 M5 的 C/D/E 裁决(⚠️ `CODE_INVENTORY.md` §7.2 明说第 2 代两文件的先后**无法从代码判定**),**须业务方定,Agent 不代判**
  - **测试一律跑隔离库 `rag_test`** —— `test_documents.py`/`test_integration.py` 会真往 `documents` 表插文档**且无 cleanup**,而那张表是 `agent-eval-gate` 评测的知识库。⚠️ 该表**历史上已被污染 29 行**(`test` 20 + `test_docs` 9),非本次引入,未清理
- **⑥ 切模块(5 个切开点,严格串行)· 进度**:
  - ✅ **切开点 1(2026-09-17)**:`db.py` 拆出 `db_metadata.py`(表声明,**零依赖**)+ `bm25_index.py`(BM25,**反向**依赖 `db.get_db`)。`db.py` 保留**函数内惰性导入**的同名转发层 ⇒ 老调用方 `from db import bm25_search` 照旧可用。**收益:`import db` 拉起的重包 4 → 0**(sqlalchemy/numpy/jieba/rank_bm25 全脱钩)
    - 门:`compileall` OK · `14`/`59` 逐位未变 · pytest **37 passed** · **R1 循环导入两个方向都测**(尤其"先 import bm25_index"那个危险序) · **R2 转发层是"真调用"验的**,非只看 import
    - 搬移保真:与原区块 diff —— **仅多 2 个空行 + 1 行 `from db import get_db`**,零内容丢失
    - ⚠️ **alembic 未实跑**(本仓 venv 没装它):`env.py` 那行改动靠**对象等价**确认,换有 alembic 的环境应补跑 `alembic upgrade head`
  - ✅ **切开点 2(2026-09-17)**:`token_tracker.py` **脱离 psycopg2**。删掉**两行重复的**模块层 `from db import get_db`(L10/L13),改为**函数内惰性导入**
    - ⚠️ **计划写的"移进函数"是单数,实测 8 个函数**用 `get_db` ⇒ **8 处各加一行**;位置放**函数体最前、`try` 之前**(放 `try` 里会被函数自己的 `except` 吞掉,掩盖 ImportError)
    - 门:`compileall` OK · `14`/`59` 未变 · pytest **37 passed** · **R2 八个函数全部"真调用"验过**(计划点名的"import 成功但首次调用才炸"风险)
    - **收益:`import token_tracker` 拉起的重包 psycopg2 → 0**
    - ⚠️ **我自己造过一次污染并已清理**:R2 冒烟**忘了带 `POSTGRES_DB=rag_test`**,往**真库 `rag_db`** 写了 4 行成本表数据(`user_name='u1'`)。已按 `u1`+`t1`+`purpose='test'` 精确删除并复核为 0;**未碰 `documents`**(评测知识库全程 70 行未变)。
      **教训:「只读冒烟」其实会写库** —— 凡调用 `record_*` 的验证必须带库名隔离
  - ✅ **切开点 3(2026-09-17)**:`code_executor.py`/`simple_tools.py` 抽 `_impl` 薄包装。新建**纯 stdlib** 的 `code_executor_impl.py`(沙箱白名单 44 builtin/9 模块 + `create_safe_globals` + `execute_python_impl`)与 `simple_tools_impl.py`(`calculator_impl`/`date_today_impl`);原文件只剩 `@tool` 外壳 + 重新导出
    - ⚠️ **收益口径要说清**:**不是**"`import code_executor` 不再拉 langchain"(**它仍然拉**——外壳建 `@tool` 必须有 langchain)。收益是**逻辑与外壳分离**:想用/想测沙箱逻辑,import **`code_executor_impl`** 即可,**不需要 langchain**
    - 门:`compileall` OK · `14`/`59` 未变 · pytest **37 passed** · 向后兼容已 grep 三个调用方(`api_v1_agent.py:19` · `agent_graph_advanced_learning.py:45` · `mcp_server.py:11,14`)
    - **🔴 工具描述逐字未变**:用 `ast` 取前后两版的 docstring 对比,`execute_python`/`calculator`/`date_today` **三者全部逐字相同**——**那是 LLM 的接口,不能动**
    - **R2 真调用**:`execute_python("print(6*7)")`→`'42\n'` · **沙箱仍拦 `import os`** ⇒ **安全边界没被削弱**
  - ⬜ **切开点 4–5 待做**:④ `main.py` gradio 挂载加环境门控 · ⑤ `api_v1_rag.py` 模块级 LLM 对象搬进函数
  - ⚠️ **严格串行,一个切开点一个 commit** —— 否则回滚粒度退化成"全部重来"
- **下一步**(在该计划之内):⬜ **⑥ 切开点 2 → 3 → 4 → 5 → ⑦ M6 单模块测试闭环**
- **⏸ 挂起项(新会话须知,别重复踩)**:
  - **凭据③ 端口收窄** ⏸ 缓期 —— **重建 `postgres-rag` 会让它与 `redis-rag` 分到不同网络**(项目已在 `#3` 改名 ⇒ 网络名从 `my-fixed-name_app-net` 变 `fastapi-rag-agent_app-net`)。**待 ⑥ 与网络改名一并处理**。口令那一半 ✅ 已完成(32 位随机,旧口令从外部连实测 FATAL)
  - **凭据④ `JWT_SECRET_KEY`** ⬜ 待办 —— `.env` 里是 169 字符、以 `eyJhbG` 开头(**像是把某个 JWT 本身填进了密钥字段**)。换掉会让**所有已签发 token 失效**
  - **`rag-api-eval` 容器是停着的** —— 2026-09-16 为了让评测打到当前代码而停(它跑的是 **2026-07-01 旧镜像**)。`agent-eval-gate` 的 harness 每次会自己 `docker run` 重建,**不用手动管**
  - **评测门判据待裁决**:同一份代码连跑三次,红队突破 **0/1/0** ⇒ **零容忍硬门 + 非确定性被测 = 会随机阻断**。属 `agent-eval-gate` 的判据,**本仓未动**(详见 `CHANGELOG.md`)
  - **本机环境**:`venv/`＝本仓自建隔离环境(Python 3.10.10,159 包/888M,**不含 torch 系**、**未装 alembic** —— 故 `alembic` CLI 跑不了;且在 `api/` 下 `import alembic` 会命中本地 `api/alembic/` **迁移目录**造成同名遮蔽,报 `No module named 'alembic.config'`,**这不算装坏了**);`.env` 有两个备份(`.env.bak-20260916*`,含全部密钥、已被 gitignore);**推送 github 间歇性挂死,先重试 2–3 次**别怀疑配置
- **已完成**:`docs/CODE_INVENTORY.md` —— 8 组代际并存、代码量(≈9,280 行)、工作量评估(删完约 −2,000 行 / 5–8 天)、逐处裁决建议。**M5 的裁决(留/并/删)本身尚未开始**
- **过程记录(常驻机制,非一次性文档)**:
  - 决策 → `docs/decisions/`(`DEC-nnn`,含备选方案与反悔成本)
  - 过程错误 → `docs/复盘/`(`YYYY-MM-DD-<主题>.md`,同一事根因不同则分记)
  - 改动 → `CHANGELOG.md`
  - ⚠️ **机制不挂在这里就等于没有** —— `api/LEARNING_INDEX.md` 已定义过一整套治理格式,**全仓库 0 个文件使用、0 个文件引用它**
- **PR 纪律(2026-09-15 起 · 依 `agent-eval-gate/docs/decisions/定调复核-签核记录.md` 的 D-23)**:
  - ⛔ **开 PR 前必须先跑 `/留痕-checks`** —— 用户级 skill,查 8 项(commit 规范 / 密钥 / 误提交 / CI / issue 关联 / **Agent 变更回归** / eval-gate / 敏感文件)。**2026-09-16 补加**:此前 8 个 PR **一次都没跑过**它(见 `docs/复盘/2026-09-16-八个PR跳过了留痕门.md`) —— **有门不用,等于没有门**
  - **一分支一 PR**;PR 模板见 `.github/PULL_REQUEST_TEMPLATE.md`(必附三项:评估回归 / 是否改 Prompt·工具·记忆 / 观测证据)
  - 开好 PR **先问业务方「可以合吗」**,拿到那句话才 `gh pr merge`(拿到后不再问第二遍)
  - ⛔ **Agent 自己开的 PR 不许自合** —— 那等于自产自合、整条链上零次人工确认;**单人仓里「点合并」是唯一的人工审核位**
  - ⚠️ **`main` 暂未开分支保护(2026-09-15 业务方决定)** —— 纪律靠本条约束,不靠平台强制。故**直接推 main 仍是可能的**,不要因为"推上去了"就以为已获批
- 本仓库是 **PUBLIC**;`main` 与 `origin/main` 保持零差异;CI 已跑绿

## 交接(2026-09-15 会话末 · 新会话从这里接)

**仓库状态**:`main` 干净、与 `origin/main` 零差异。CI 已 green。

**本次做了什么**:
1. 确认 GitHub 链路可用(`git ls-remote` 通;`gh` 已登录账号 `heweidong-ecco`)
2. 删除已合并的残留分支 `docs/api-doc-final-review`
3. 新增 CI 骨架 `.github/workflows/ci.yml` —— 只跑 `compileall`(钉 Python 3.10,与 `api/Dockerfile` 一致),**不含 pytest**;首次运行 conclusion=success
4. 新增本文件

**M5 的由来(业务方 2026-09-15 原话口径)**:
> 这个项目里面,比如一个结构和文件存在多种代码,基础版、进阶版、更新版、混合版,不同内容。我现在需要裁决和合并,删除里面的部分内容,到能跑。需要做一次盘点,和总体代码量以及工作量的评估,确定后期内容。再单独给个模块做完整测试闭环。

## 里程碑

| ID | 里程碑 | 产出 | 验收 | 状态 |
|---|---|---|---|---|
| M0 | 主体功能搭建 | FastAPI + pgvector + Redis + LangGraph Agent;检索三模式/混合检索/重排序/SSE/双认证/限流配额 | 接口可跑通 | ✔ |
| M1 | 全面复审 | `CLAUDE.md` 记录的 **24 项修复**(启动崩溃/认证失效/数据丢失等) | 修复入库 | ✔ |
| M2 | 实机验证修复 | 3 个 commit:LLM env 可配、查询改写空返回回退、BM25 缓存失效 | 实机跑通 | ✔ |
| M3 | 搬运至 GitHub + 链路验证 | 仓库创建(2026-08-17)、本地↔远端同步确认 | 零差异 | ✔ |
| M4 | CI 骨架 | `.github/workflows/ci.yml`(compileall, Python 3.10) | Actions 首次跑绿 | ✔ |
| M5 | **代码盘点与裁决合并** | ①代际并存清单 ②逐处裁决(留/并/删) ③**代码量 + 工作量评估** ④删到能跑的最小集 | 盘点表齐 + 评估可据以排期 | ⬜ |
| M6 | **单模块完整测试闭环** | 选定**一个**模块,打通"改代码 → 跑测试 → 看结果"的完整闭环(作先例) | 该模块测试可一键重复跑 | ⬜ |
| M7 | 全量测试与评估接入 | pytest 全套 + RAGAS 评估复跑 | 待 M5/M6 定案后定 | ⏸ |

## 已登记、暂不处理

| 项 | 来源 | 说明 |
|---|---|---|
| `bad_cases.md` 三项 | 2026-06-28 评估 | `answer_relevancy` 仍为 NaN;`context_precision` 仅 0.4369(当时未开 rerank);评估集缺拒答类样本 |
| `硬性指标终极核查清单.md` 28 项未勾 | 本仓库文档 | P99/失败率/并发/Grafana 等尚无实测数据 —— M7 的验收依据 |
| Agent 各类死代码 | `CLAUDE.md` | `'''...'''` 注释保留的旧实现,不影响运行;M5 盘点时统一裁决 |

> **M5 开工前建议先读**:`CLAUDE.md` 的「关键开发模式」与「认证与授权」两节 —— 那里记着几个"看着安全实则有坑"的契约(中间件抛异常不被捕获、`HTTPBearer` 必须 `auto_error=False`、`get_db()` 连接池契约)。**删代码前先知道哪些是承重墙。**
