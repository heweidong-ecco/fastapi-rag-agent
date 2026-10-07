# DEC-093 · 段 1 第六刀：**Trace 页**，与「两条轴拼不成一棵树」

> 🔴 **刀次勘误（2026-10-06 本份自查）**：本文件与施工单起初都写「**第三刀**」—— **写错了**。
> `ROADMAP.md` 的**现行编号**是：① 对话页（`DEC-085`）② 接管页（`DEC-088`）③ **引用卡片**（`DEC-089`）
> ④ 熔断卡片（`DEC-090`）⑤ 无据拒答（`DEC-091`）⇒ 本份是 **⑥**。
> ⚠️ **错因**：把「**第 3 个面向人的页面**」（`/chat` → `/approvals` → `/trace`，这个**是对的**）
> 顺手写成了「第三刀」—— **两个不同的计数共用一个词根**，本仓的老形态。
> 📌 **判据（可打印）**：`grep -n '段 1 第.刀' ROADMAP.md docs/decisions/DEC-0*.md` ⇒ 逐条对号。

| 项 | 内容 |
|---|---|
| **状态** | 🟢 **已实现**（2026-10-06）—— 设计已在会话内过完业务方**一次裁定**（§一，选「乙 · 两轴分屏」） |
| **落地单** | `fastapi-rag-agent-TODO待办/施工单-20261006-Trace页.md`（9 个 Task · 命令级）· 分支 `feat/trace-page` |
| **触发** | `ROADMAP` 的 `⬜ Trace 页`（`docs/待办总表.md` §三·附2 的 **`F2`**）<br>⚠️ 它同时是 **`docs/FAQ.md` 里一条对外承诺地址**的所在地（旧链接 `/static/trace_viewer.html`） |
| **业务方裁定** | **一条**：范围选「**乙 · 两轴分屏**」（§一）。⚠️ 那是在本份**核出「原措辞无单一数据源」之后**才给出的选项 |
| **类型** | 🆕 第 3 个面向人的页面 · 🆕 一个只读端点 · 🔧 **既有模块 `token_tracker` 加一个函数**（⛔ 不新增模块） · 🔧 **新建的 `F2` 界面替换掉一个存量坏页** |
| **落点** | `api/token_tracker.py` · `api/api_v1_agent.py` · `api/main.py` · `api/static/web/trace.html`（新）· `api/static/js/trace.js`（新）· `api/static/js/trace.test.js`（新）· `api/test_trace_cost.py`（新）· `api/test_trace_cost_db.py`（新）· `api/test_trace_page.py`（新）· `api/static/trace_viewer.html`（**只加横幅，不删**）· `.github/workflows/ci.yml`（+1 行 `node --test`）· `scripts/route-auth-baseline.txt` · `docs/FAQ.md` · `docs/specs/` 五份 |
| **判据** | §五 —— 全部**可打印**（**已填实测数**） |

> 📌 **行号基准 = `d709aa5`**（`#109` 合并后的主干）。
> **定位一律用命令，⛔ 别抄行号**：
> ```bash
> grep -n 'async def agent_trace_detail' api/api_v1_agent.py    # ⇒ 2089（新端点加在它后面）
> grep -n 'def get_thread_cost' api/token_tracker.py            # ⇒ 899（⛔ 别复用它，理由见 §三·A）
> grep -n '@app.get("/approvals"' api/main.py                   # ⇒ 547（要照抄的那条 302）
> grep -n 'node --test' .github/workflows/ci.yml                # ⇒ 3 行（⛔ 少一行 = 那份用例永不跑）
> ```

---

## 一 · 业务方裁定（一条）

| # | 事项 | 裁定 | 备选 / 为什么没选 |
|---|---|---|---|
| **1** | **`F2` 的页面画什么** | **乙 · 两轴分屏** —— 上半天画**追踪轴**（工具调用逐步耗时），下半天画**成本轴**（逐笔 token / 花费），**⛔ 不合成一棵树** | 见 §二：`F2` 原措辞隐含"一棵带 token/耗时/成本的 span 树"，而**那棵树的数据不存在**。①**甲 · 硬凑成树** —— 得靠"时间接近"猜对应关系，**凑出来的层级是编的**，而且不报错（本仓最恨的形态）；②**丙 · 只做成本轴** —— 会把现存的追踪轴页面直接作废，而它记的"哪个工具慢"是成本轴**没有**的信息 |

---

## 二 · 核出来的事：`F2` 原措辞**没有单一数据源**

`docs/待办总表.md` §三·附2 对 `F2` 写的是「span 树 + 每步 token/耗时/成本」。
**动手前先核数据源，发现这两样东西分属两条轴，而且拼不到一起**：

| | **追踪轴** | **成本轴** |
|---|---|---|
| 存储 | `api/tool_visualizer.py` 的 `_traces` —— **进程内存** | PG 表 `token_usage_logs` |
| 粒度 | **工具调用**（`tool_name` / `duration_ms` / `result[:500]`） | **模型调用**（`model` / `purpose` / `prompt_tokens` / `cost`） |
| 谁在写 | **只有 `mcp_agent_chat` / `mcp_agent_chat_stream`**（`start_trace(` 全仓 **2 个**调用点） | **所有花钱的地方** |
| 共同的步 id | ⛔ **没有** | ⛔ **没有** |

⇒ **两轴能对上的只有 `(user_name, raw thread_id)` 这一对游标**（实测 `session_key` 就是把这两个拼起来）。
**再往下就对不上** —— 一个 `agent_decision`（模型调用）与一个 `search`（工具调用）之间**没有可判定的对应**。

> 📌 这条不是"实现细节"，是**方案选择的前提**：能对上的话甲案（合成树）就成立，对不上就不成立。

### 顺带核出的两件事（都写进了页面）

1. 🔴 **现有那两格概览卡【从上线起就是假的】** —— `trace_viewer.html` 印的
   `'¥' + (trace.total_cost || 0).toFixed(4)` 与 `trace.total_tokens || '--'`，
   而 `finish_trace(user_name, thread_id, <answer>)` 的**两个调用点都没传这两个值**
   ⇒ 它们**恒为 `¥0.0000` / `--`**。⚠️ 这不是"以后再补"，是**把假数据印给人看**。
2. 🔴 **演示路径上，上半页【必然】是空的** —— `/chat` 走的是 `/api/v1/rag/stream_search`，
   那条链**不调 `start_trace`**。⇒ 页面**必须解释"为什么空"**，⛔ 不许只印一句"未找到"
   （否则看的人会以为整个功能坏了）。

---

## 三 · 四处具体化（⚠️ 不是改裁定，是把它落到实处）

| # | 设计时的措辞 | 落地成 | 为什么 |
|---|---|---|---|
| **A** | 「取数函数放进既有模块 `token_tracker.py`」 | 新函数 **`thread_cost_breakdown(user_name, thread_id, *, include_all=False)`**，**⛔ 不碰**旁边那个 `get_thread_cost(thread_id)` | **发现**：`get_thread_cost` 签名上**没有 `user_name`** —— 看起来像越权洞。**实测不是**：全仓**唯一**调用点是 `token_tracker.py:888` 的线程预算检查，用的正是调用者**自己的** thread_id。⇒ **不改它**（改它要动预算逻辑、有回归风险），而是在 `docs/specs/token_tracker.md` 里**写明它是"像洞而不是洞"**，并把两个版本**并排放着** —— 下一个读到的人自然会看见差别 |
| **B** | 「时间要显式处理」 | 后端 `_iso_utc()` 一律回**带 `+00:00`** 的 ISO；前端 `parseWhen()` **主动拒绝**不带区的时间戳（回 `--`） | **发现**：`created_at` 的类型是 **`TIMESTAMP`（无时区）**，而 PG 容器 `SHOW timezone` = **`Etc/UTC`** ⇒ 存的是**裸 UTC**。原样回 `2026-10-06T13:14:21`，JS 会当**浏览器本地时间**解析 ⇒ 东八区用户看到的时刻**静默早 8 小时**。（同族前科：`logs/api_*.log 混了两套时区`。）⚠️ **`approval_audit` 用的是 `TIMESTAMPTZ`、天生带区，⛔ 别照抄它的 `.isoformat()`** |
| **C** | 「thread_id 要防空串」 | **本端点不需要守卫** | **发现**：它是 **path 参数** —— 空串在 URL 里变成 `/agent/trace//cost`，**根本匹配不到这条路由**（自带 404）。`F6` 那两条是 **query** 参数，才是真会传空串的地方。⇒ ⛔ 不无脑抄 `Query("default", min_length=1)`（那会给一个**已经不会发生的**错误加守卫，读代码的人会以为这里真会空） |
| **D** | 「删掉两个假卡」 | 删的是概览里的「**总 Token**」/「**总花费**」两格；**耗时**与**工具次数**留着 | 概览那一栏的来源**只有追踪轴**，那两个字段在那里恒为 0。留着 = 把「假完成」印在页面上（硬门 C 的原话就是「最容易假完成」）。真金额在下半页，那里是**查库**的 |

### 额外一处（不在设计里，是**变异实验**照出来的）

`thread_cost_breakdown` 第一版把「条件句」与「它的参数」写成**两个独立的三元表达式**：

```python
owner_clause = "1 = 1" if include_all else "user_name = %s"
owner_params = () if include_all else (user_name,)
```

⇒ **改一处不改另一处 ⇒ 参数个数对不上 ⇒ 运行期 SQL 报错**。
变异实验（把 `owner_clause` 单独改成 `"1 = 1"`）没让 `test_empty_key_normalized_to_unknown` 变红，
就是这条漏出来的。⇒ 已改成**同一个 `if` 里一起定**，结构上漂不了。
📌 这是本仓「**只有文字就漏，结构才执行**」的又一例。

---

## 四 · 🔴 本批顺带核出的一个**真事故**（⛔ 不在本批范围内，未修）

**`api/static/web/approvals.html`（`DEC-088` · `F1` · PR `#105`，2026-10-06 合入）在浏览器里跑不起来。**

它 fetch 的 4 条 URL **全少 `/api/v1`**：

```text
/agent/pending               ← 真实路由是 /api/v1/agent/pending
/agent/pending/context?
/agent/approve?
/agent/approvals/history?
```

**判据（可打印，读真实路由表）**：

```bash
venv/bin/python -c "
import sys,warnings; warnings.filterwarnings('ignore'); sys.path.insert(0,'api')
from fastapi.testclient import TestClient; from main import app
c=TestClient(app)
print('/agent/pending        ->', c.get('/agent/pending').status_code)          # ⇒ 404
print('/api/v1/agent/pending ->', c.get('/api/v1/agent/pending').status_code)   # ⇒ 401（路由在，只是要鉴权）
"
```

**为什么没有任何用例红**（三条都不报错）：

| 层 | 为什么漏 |
|---|---|
| `api/test_approvals_page.py`（3 条） | 只看 `GET /approvals` 的 **302 与跳转目标**，⛔ 不看页面脚本里的 URL |
| `api/static/js/approvals.test.js`（14 条） | 全是**纯函数** —— `buildContextQuery()` 只回 **query string**，前缀根本不经过它 |
| `scripts/check_route_auth.py` | 它管的是「**后端有没有多余的无鉴权路由**」，与页面打什么 URL 无关 |

⇒ **URL 前缀硬编码在那一行 HTML 里，而那一行没有任何判据。**

**本刀当时的处理（⛔ 不顺手修）**：① 登记进 `docs/待办总表.md`（**`N15`**）；
② **把这条缺口变成判据** —— 当时落在 `api/test_trace_page.py::test_page_url_literals_carry_the_api_prefix`，
**只对 Trace 页生效**（实测把它拿去跑 `approvals.html` 会把 4 条全拦下）；
③ **是否回头修 `approvals.html` 交业务方裁**（§六·待裁 2）。

> ✅ **2026-10-06 已裁并已做**（业务方：**「现在修，并进 `F2` 这个 PR」**）⇒
> **4 条 URL 全部补上 `/api/v1`**，「本批不修」那句**已作废**。
> ⚠️ 同时**那条守卫搬了家** —— 从本刀只盯 `trace.html`，改成
> **`api/test_web_pages.py` 扫 `api/static/` 下每一个 `.html`**
> （⚠️ **本文件下文凡写"守卫在 `test_trace_page.py`"的，一律以这条为准**）。
> 📄 **全文（含为什么⛔ 没改 helper 拼路径、glob 的反证实测）** ⇒ `DEC-094`。
> 🔴 **`DEC-051` 先例**（只允许顺手修**同一功能**的邻近缺陷）**没有作废** ——
> 这是一次**业务方拍下的例外**，⛔ 别当先例引用。

---

## 五 · 判据（全部可打印，**已填实测数**）

```bash
node --test api/static/js/trace.test.js                                     # ⇒ 24 pass, 0 fail
venv/bin/python -m pytest api/test_trace_cost.py api/test_trace_page.py -q  # ⇒ 22 passed
POSTGRES_DB=rag_test venv/bin/python -m pytest api/test_trace_cost_db.py -q # ⇒ 9 passed
venv/bin/python scripts/check_route_auth.py --baseline; echo "exit=$?"      # ⇒ exit=0（无鉴权路由 3 → 4）
bash scripts/ci-local.sh                                                    # ⇒ exit 0
                                                                            #    pytest 794 passed, 3 skipped, 40 deselected
```

**本刀当时没有修 `approvals.html`** ⇒ 那时上面四条判据**都不涉及它**（这也是它当时绿着的原因之一）。
⚠️ **2026-10-06 已经修了**（§四末）⇒ 现在多两条判据，见 `DEC-094` §五。

### ⚠️ 判据的**反证检验**（逐条做过，⛔ 不是"跑了就算"）

| 变异 | 应当红的 | 实测 |
|---|---|---|
| `owner_clause` 永远 `"1 = 1"`（= 照隔壁抄） | 明细 / 合计 / 空串 三条 | ✅ 4 红 |
| 端点永远传 `include_all=True` | `..._does_not_grant_include_all_to_others` | ✅ 1 红 |
| SQL 去掉用户过滤（**真库**） | 越权 / 合计 / admin 默认 三条 | ✅ 3 红 |
| `parseWhen` 去掉"不带区就拒" | `parseWhen 拒绝不带时区的时间戳` | ✅ 1 红 |
| `summarizeCost` 改成把 rows 加起来 | `...⛔ 不把 rows 加起来` | ✅ 1 红 |
| 页面路径改成裸字面量 `'/agent/...'` | URL 前缀两条 | ✅ 2 红 |
| 概览卡加回「总花费」 | `..._does_not_print_the_two_dead_overview_cards` | ✅ 1 红 |
| 基线注释掉 `/trace` | 路由门 | ✅ exit=1 |

> ⭐ 其中**前三条**正是本仓 2026-10-05 那条纪律的落地：**先问「把结论取反，这条命令的输出会变吗」**
> —— 变不了 ⇒ 那条判据根本没在测那件事。

---

## 六 · 遗留（⛔ 本批**不做**的事，逐条写清为什么）

1. **其余 Agent 链不建轨迹** —— 全仓只有 2 处调 `start_trace`。补上它们，上半页在演示时才有东西。
   ⛔ 本批不做：那是改**后端链**，与"建一个页面"是两件事；且它会让本批的判据面从"读"扩到"写"。
   ⇒ **登记为债**。
2. **追踪轴是进程内存，重启即空** —— 与 `/agent/pending` 同一形态。
   ⛔ 本批不做搬运（要新建表 + 改 2 个调用点 + 迁移）。⇒ **登记为债**，但**页面上明写了这一句**。
3. **`agent_decisions` 的形状** —— 服务端是 `List[dict]`，形状**不保证**（`record_agent_decision`
   直接把调用方的 dict 追加进去）。⇒ 前端只做"能读就读"的摘要，⛔ 不假设键名。
4. **旧页 `api/static/trace_viewer.html` 保留**（只加横幅）—— 因为 `docs/FAQ.md` 写过它的地址，
   删掉会让那条指引落到 404。
5. **⛔ 本批不动 `token_tracker.get_thread_cost`** —— 见 §三·A。
6. **⛔ 本批不动 `api/static/stream_test.html`** —— `F5`，`DEC-085` §六·4 明文挂着。

### §待裁 —— ✅ **2026-10-06 已全部裁定**（⛔ 本 Agent 一条都没自拟）

1. **PR 频率** —— 2026-10-06 当天已开 8 个 PR（`#102`–`#109`）。本刀是现在开还是攒着？
   ⇒ **业务方裁：⛔ 先不开，等发话。**
2. **`approvals.html` 的 `/api/v1` 前缀要不要现在修**（§四）—— 4 行字符串，页面**目前 100% 不可用**。
   ⇒ **业务方裁：✅ 现在修，并进本刀的 PR。**（🏁 **`N15` 已结清**）
3. **`.github/workflows/ci.yml` 的 `node --test` 要不要改成 glob** ——
   现在是**逐个列名**（`sse` / `approvals` / 现在加 `trace`）。
   ⇒ **新增一个 `.test.js` 而忘了加行 = 那份用例永不跑，且没有任何门会红**（本批已踩过一次边缘）。
   ⇒ **业务方裁：✅ 改。**（🏁 **`N18` 已结清**）
   🔴 ⚠️ **落地时反证照出一件事**：**裸 glob 比逐名列名更弱** —— 一个都匹配不上时
   `node --test` 回 **`tests 0` / 退出码 0**（逐名列名是 `Could not find …` / **退出码 1**）。
   ⇒ **不能只换一行**，必须连防空跑一起写。📄 `DEC-094` §三·B

> 📄 **三条裁定的全文 + 落地细节 + 反证表** ⇒ `docs/decisions/DEC-094-前缀事故收尾与CI用例改glob.md`
