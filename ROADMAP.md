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
  - ✅ **切开点 4(2026-09-17)**:`main.py` 的 Gradio 挂载加环境门控(`ENABLE_DASHBOARD`,**默认 `"true"` 保持现状**,业务方裁决 A 方案)
    - 🔴 **收益口径**:给的是「**可以**不拉 gradio+matplotlib」,**不是**「不再拉」——**默认路径上仍然拉**;只有显式设 `false` 才真省掉。**这条写进了代码注释**,免得后人按错的预期用
    - **两条分支都测**(只测默认分支等于没测收益分支):🅰默认 `14`/`59` 逐位一致、gradio 仍拉 · 🅱`false` 时 `13`/`59`、`/dashboard` 消失、gradio 与 matplotlib **都没拉**
    - 📌 `OPENAPI_PATHS` 两边都是 59 —— `/dashboard` 是 **mount 不是 OpenAPI 路由**;`app.routes` 掉 1 正印证计划 R5 那个坑:**L516 会重绑定 `app`**
    - 门:`compileall` OK · pytest **37 passed**
  - ⬜ **切开点 5 待做**:⑤ `api_v1_rag.py` 模块级 LLM 对象搬进函数
  - ⚠️ **严格串行,一个切开点一个 commit** —— 否则回滚粒度退化成"全部重来"
- **下一步**(在该计划之内):⬜ **⑥ 切开点 4 → 5 → ⑦ M6 单模块测试闭环**(① ② ③ 已完成)
- **⏸ 挂起项(新会话须知,别重复踩)**:
  - **凭据③ 端口收窄** ⏸ 缓期 —— **重建 `postgres-rag` 会让它与 `redis-rag` 分到不同网络**(项目已在 `#3` 改名 ⇒ 网络名从 `my-fixed-name_app-net` 变 `fastapi-rag-agent_app-net`)。**待 ⑥ 与网络改名一并处理**。口令那一半 ✅ 已完成(32 位随机,旧口令从外部连实测 FATAL)
  - **凭据④ `JWT_SECRET_KEY`** ⬜ 待办 —— `.env` 里是 169 字符、以 `eyJhbG` 开头(**像是把某个 JWT 本身填进了密钥字段**)。换掉会让**所有已签发 token 失效**
  - **`rag-api-eval` 容器是停着的** —— 2026-09-16 为了让评测打到当前代码而停(它跑的是 **2026-07-01 旧镜像**)。`agent-eval-gate` 的 harness 每次会自己 `docker run` 重建,**不用手动管**
  - **评测门判据待裁决**:同一份代码连跑三次,红队突破 **0/1/0** ⇒ **零容忍硬门 + 非确定性被测 = 会随机阻断**。属 `agent-eval-gate` 的判据,**本仓未动**(详见 `CHANGELOG.md`)
  - **🔴 本机硬件实况(2026-09-17 实测,回答过"是硬件不够还是代码问题")**:
    **8.0 GB 物理内存** · 4 核 Intel i5-7600 · 磁盘可用 **452 GB(磁盘完全不是瓶颈)** · Docker 配额 **3.84 GiB** · 当前空闲内存 **≈105 MB**
    - **结论:硬件不够是真的,但只卡住【两条路】**:① `docker build` 完整镜像(宿主 8GB + Docker 只分 3.84GB)② `mode=accurate/full` 与 `rerank_search`(要 torch ~1GB + 模型 `bge-reranker-v2-m3` **2.3GB**)
    - **⚠️ 不是代码/业务问题 —— 恰恰相反,代码是对的**:`reranker.py:14` 是**真懒加载**、默认 mode 是 `accurate_norerank` ⇒ **默认路径根本不碰 torch**,所以"没装 torch"**不会让应用起不来**
    - ⇒ **硬件挡住的是【验证覆盖面】,不是【业务能力】**。换大内存机器 `mode=accurate/full` 就能验,**产品本身没有缺陷,是验证有个洞**
    - ⚠️ 准确说法是**"没有余量、高风险"**,**不是"物理上不可能"**(8GB 塞 torch+模型≈3.3GB 峰值,理论塞得下但会疯狂 swap)。业务方 2026-09-17 裁决:**不值,不去撞**
    - (已实测确认:torch / transformers / sentence_transformers / cv2 / ragas / datasets / locust **一个都没装**;gradio 与 matplotlib **有**)
  - **本机环境**:`venv/`＝本仓自建隔离环境(Python 3.10.10,159 包/888M,**不含 torch 系**、**未装 alembic** —— 故 `alembic` CLI 跑不了;且在 `api/` 下 `import alembic` 会命中本地 `api/alembic/` **迁移目录**造成同名遮蔽,报 `No module named 'alembic.config'`,**这不算装坏了**);`.env` 有两个备份(`.env.bak-20260916*`,含全部密钥、已被 gitignore);**推送 github 间歇性挂死,先重试 2–3 次**别怀疑配置
- **已完成**:`docs/CODE_INVENTORY.md` —— 8 组代际并存、代码量(≈9,280 行)、工作量评估(删完约 −2,000 行 / 5–8 天)、逐处裁决建议。**M5 的裁决(留/并/删)本身尚未开始**
- **过程记录(常驻机制,非一次性文档)**:
  - 决策 → `docs/decisions/`(`DEC-nnn`,含备选方案与反悔成本)
  - 过程错误 → `docs/复盘/`(`YYYY-MM-DD-<主题>.md`,同一事根因不同则分记)
  - 改动 → `CHANGELOG.md`
  - ⚠️ **机制不挂在这里就等于没有** —— `api/LEARNING_INDEX.md` 已定义过一整套治理格式,**全仓库 0 个文件使用、0 个文件引用它**
- **PR 纪律(2026-09-15 起 · 依 `agent-eval-gate/docs/decisions/定调复核-签核记录.md` 的 D-23)**:
  - ⛔ **开 PR 前必须先跑 `/留痕-checks`** —— 用户级 skill。**2026-09-16 补加**:此前 8 个 PR **一次都没跑过**它(见 `docs/复盘/2026-09-16-八个PR跳过了留痕门.md`) —— **有门不用,等于没有门**
  - ⛔⛔ **同一时点还必须过一遍 A 级 skill** —— **2026-09-17 补加,起因是它又被跳过了**:
    `CLAUDE.md` 的 A 级表写着 9 个「命中必须用」,但**切开点 3 期间命中 4 个、一个没调**
    (见 `docs/复盘/2026-09-17-写了必用表自己却没用.md`)。
    **根因**:「命中必须用」是一句**判据**,不是**动作** —— 没有哪个瞬间逼我停下来核对它;
    而 `/留痕-checks` 能生效,正因为它是**「开 PR 前必须先跑」这个动作**。
    ⇒ **现绑到同一检查点。开 PR 前逐条写出结论,三选一:**

    | 时点 | 该核的 A 级 skill |
    |---|---|
    | **提交 / 开 PR 之前** | `verification-before-completion`(**evidence before assertions**) |
    | **合并之前** | `requesting-code-review` · `finishing-a-development-branch` |
    | **执行书面计划时** | `executing-plans` |
    | **动代码之前** | `writing-plans`(无计划时) · `test-driven-development`(写新功能/修 bug 时) |
    | **遇到 bug / 测试失败 / 异常** | `systematic-debugging`(**提出修法之前**) |
    | **收到 review 意见时** | `receiving-code-review` |
    | **做创造性工作之前** | `brainstorming`(⚠️ ≈20k,见 `CLAUDE.md`) |

    ⚠️ **每条都要写出结论**:**「调了」/「未命中(为什么不命中)」/「命中未调(说明原因)」**。
    **不许只写"已核对"** —— 那等于没写(本次复盘就是证据:**产出物上看不出判据被跳过**)。
  - ⛔⛔ **同一时点还要过一遍「三套过程记录」** —— **2026-09-17 补加,起因是 `DEC` 那一路断了**:

    | 渠道 | 记什么 | 触发器 | 本仓实况 |
    |---|---|---|---|
    | `CHANGELOG.md` | **改了什么** | ✅ **每次 commit 自然就写** | ✅ 正常 |
    | `docs/复盘/` | **过程错在哪** | ✅ **出错就写**(可感知的事件) | ✅ 正常 |
    | `docs/decisions/` | **为什么这样选** | ⛔ **没有** —— 要先判定"这事算不算决策" | ⛔ **停在了 `DEC-001~004`(全是 09-15)** |

    > 🔴 **断因不是"没挂进 ROADMAP"** —— 机制**一直**挂在当前指针里(每轮都读得到)。
    > 断因是**它只绑在【判据】上("这算不算决策?"),没绑在【动作】上**。
    > 前两套绑在动作上(commit / 出错),所以活着;**`DEC` 绑在判据上,所以死了**。
    > ⚠️ **这与 A 级 skill 那次是同一个病**(见 `DEC-007`、`docs/复盘/2026-09-17-写了必用表自己却没用.md`)。
    > 而且 **`DEC-004` 自己就预言过**:「本决策的最大风险不是"建不建",而是"**建了不用**"」——**它中了**。

    **⇒ 修法:在 PR 那一刻强制问一次** ——
    > **「这次改动里,有没有在多个方案之间做过选择?」**
    > · **有** ⇒ **建一份 `DEC-nnn`**(含备选方案 / 评估标准 / 反悔成本)
    > · **无** ⇒ 在 PR 里写明「**本次无决策事项**」
    > ⛔ **不许不写** —— 不写 = 判据里没这一步 = 本仓已犯过三次的那个错。
  - ⚠️ **2026-09-17 适配裁决**:该 skill 查 **8 项**,但在本仓**只有 5 项适用**。**仍要调 skill,但只报这 5 项**;另 3 项**一行带过写「不适用」**,不逐条展开:

    | 报 | 项 | 本仓判据 |
    |---|---|---|
    | ✅ | ① commit 规范 | Conventional(`type(scope): …`),一条一件事 |
    | ✅ | ③ 密钥扫描 | 🔴 **本仓是 PUBLIC** —— **跑 `bash scripts/check_secrets.sh`**（**命中即 `exit 1` 中止**）。⚠️ **不许再手敲 grep** —— 那只打印不中止,是"报告"不是"门"（见下）|
    | ✅ | ④ CI 状态 | `gh pr checks`。⚠️ **不凭命令输出判成败**(#13 那次 pending 假象) |
    | ✅ | ⑥ 误提交文件 | 新增文件是否都在合理位置 |
    | ✅ | ① 未提交/未跟踪 | 有无残留临时文件(如曾经的 `api/_tmp_olddb.py`) |
    | ⬜ | ⑤ issue 关联 | **不适用** —— 本仓无 issue 体系,恒为「无」 |
    | ⬜ | ⑧ eval-gate | **不适用** —— 本仓 CI 无评估门,且这是**已登记**的延期状态(`ci.yml:4` 待 M6) |
    | ⚠️ | ⑦ Agent 变更回归 | **判据须改写**(见下) |

    > **为什么砍 #5/#8**:它们**4 次运行输出逐字相同**——问的是"本仓有没有 X",答案恒为没有。
    > **那不是"发现问题",是每次重新发现同一个事实**。而一个**每次都是红的门会被读成已知噪音然后被忽略**,
    > 连带**稀释掉真正有用的那 5 项**。
  - ⚠️ **③ 密钥扫描为什么必须用脚本、不许手敲 grep(2026-09-17 事故)**:
    当天我把 **3 个历史泄露凭据的字面量写进了 PUBLIC 文档**,手敲的 grep **报了 `hits=1`×3** ——
    **但 commit 照样落地了**(靠 `--amend` 才救回)。**它只打印,不中止。那不是门,是一份报告。**
    ⇒ **判据 vs 动作** —— 本仓第 N 次栽在同一个坑上。已改为跑 `bash scripts/check_secrets.sh`(**命中即 `exit 1`**)。
    ⚠️ **同一事故的第 3 次**,是在**起草 PR 正文**时又写了一遍,被**外部分类器**拦住 ——
    **是外面的门救的,不是我自己的门**。这正是本条要固化的原因。
  - ⚠️ **#7「Agent 变更回归」的本仓判据(双判据,2026-09-17 裁决)**:
    - ⛔ **原判据在本仓失效**:它按**路径**触发(`prompts/` · `contracts/tools-mcp` · `eval/`),
      且那些路径**相对 `agent-eval-gate` 而非本仓**。**本仓 prompt 是内联在 `.py` 里的**
      ⇒ 路径式触发**永不命中**,哪怕 prompt 真被改了
    - ✅ **判据 A(快·文件清单)** —— 本仓 prompt / 工具 / 记忆 的**真实分布**,
      **实测得来**(2026-09-17 扫全 `api/*.py`,非手写):

      | 面 | 文件 |
      |---|---|
      | **prompt** | `agent_graph_advanced_learning.py`(7) · `plan_execute.py`(6) · `rag_pipeline.py`(3) · `api_v1_rag.py`(3) · `agent_graph_advanced.py`(3) · `query_rewriter.py`(2) · `search_tools.py`(1) · `answer_with_citations.py`(1) |
      | **工具** | `mcp_server.py`(5) · `mcp_tool_factory.py`(5) · `agent_graph_advanced_learning.py`(4) · `browser_tools.py`(3) · `api_v1_rag.py`(3) · `simple_tools.py`(2) · `agent_graph.py`(2) · `agent_checkpointer.py`(2) · `code_executor.py`(1) · `search_tools.py`(1) |
      | **记忆** | `memory_store.py`(12) · `agent_graph_advanced_learning.py`(6) · `agent_graph_advanced.py`(3) · `api_v1_agent.py`(2) |

      ⚠️ **清单可重生成**(不靠记)——
      ```bash
      cd api && for f in *.py; do
        p=$(grep -cE "system_prompt|system_message|你是一个|请严格根据" "$f")
        t=$(grep -cE "@tool\b|@server\.(list_tools|call_tool)|TOOL_HANDLERS" "$f")
        m=$(grep -cE "Mem0|mem0|from memory_store" "$f")
        [ $((p+t+m)) -gt 0 ] && echo "$f prompt=$p 工具=$t 记忆=$m"; done
      ```
      📌 **本清单的来历**:第一版是**我手写的 7 个**,当场验证发现**只覆盖约 40%**
      —— 实际 18 个文件,漏了 11 个(最大一处 `agent_graph_advanced_learning.py`)。
      **手写清单被当场证伪** ⇒ 故改为「方法 + 派生结果」,并保留这条教训。
    - ✅ **判据 B(慢·内容兜底)**:不看路径,直接看 **diff 有没有改 prompt 文本 / 工具 schema / 记忆策略**
    - **两者都要** —— A 快但**清单会腐**(已证伪一次),B 慢但**不会漏**
    - ⚠️ **用了哪个判据要在 PR 里说出来**;用了替代判据**必须写明**,
      **不许静默翻译判据**(规则见 `docs/规则草稿-规则必须绑定路径.md`)
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
