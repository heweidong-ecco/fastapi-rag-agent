# 施工单 · 2026-10-09 · **langchain-core 0.3 → 1.x 连锁升级**（实施计划）

> **给执行者**：本计划**分两相**。**Phase 1 必须先做完、并落下实测失败清单**；
> Phase 2 的修复任务**由那份清单驱动** —— ⛔ **不许凭空写**（本仓已记过多次"假完成"）。
> 相变点就在 Task 4，那里有明确的"停一下、重新规划"的门。

**Goal：** 把 `langchain-core` 0.3.86 拉到 1.x，连带清掉 `SECURITY.md` §3.4 里
剩下 19 条依赖漏洞中的 **17 条**（`pyjwt` 那 2 条已于同日单独清掉）。

**Architecture：** 这是**一次依赖大版本连锁**，不是新功能。做法是
**先把真实约束跑出来（dry-run），再动 venv，再让 913 条测试告诉我们哪里坏了** ——
⛔ 不许靠"我记得 1.0 里删了 XX"来改代码。

**Tech Stack：** Python 3.10 · FastAPI · langchain / langgraph 全家桶 · `venv/`（本机唯一环境）

**Spec：** `SECURITY.md` **§3.4**（依赖闭包图 + pip 报错原文，**权威**）·
`fastapi-rag-agent-TODO待办/施工单-20261009-安全收尾两项-接续.md` §二

---

## Global Constraints（每个 Task 都隐含适用）

- **分支**：`fix/dep-upgrade-batch1`（已推 origin，含 `pyjwt` 那一笔 `123b60d`）
- **`app/requirements.txt` 是全 `==` 钉死的** ⇒ 升级 = **改那 40 行里对应的几行**，
  ⛔ 不是加 `>=`（那会把刚钉好的又松开）。改完那条判据必须仍然成立：
  `grep -cE '^[A-Za-z][^#]*==' app/requirements.txt` ⇒ **40**
- **基线（改动前后都要能复现）**：
  `./venv/bin/python -m pytest app/ -m "not integration and not needs_db" -q` ⇒ **913 passed / 2 skipped**
- **全量门**：`bash scripts/ci-local.sh` ⇒ **退出码 0**
- **文档门**：`check_doc_links.sh` · `check_doc_orphans.sh` · `check_index_sync.sh` ⇒ **三个 exit 0**
- 🔴 **真服务验证是本轮的必做项**（改的是 LLM 调用链）——
  ⛔ "测试全过"在本仓**不算**这条的凭证（有前科：单测 21 条全绿而真服务 500）
- ⚠️ **`openai` 那一层不在原 8 个包里**（见 Task 2），它落在 **RAG 主路径**上

---

## 已查实的依赖闭包（2026-10-09 实测，⛔ 不是推断）

```
langchain-core  0.3.86 → >=1.2.31        ← 总闸
   ├─ 逼 langchain                0.3.30  → 1.x
   ├─ 逼 langchain-openai         0.2.14  → 1.1.14+  ⇒ 🔴 再逼 openai 1.109.1 → >=2.26.0,<3.0.0
   ├─ 逼 langchain-text-splitters 0.3.11  → 1.1.2
   └─ 逼 langgraph                1.0.1   → 1.0.10   ⇒ 连带 langgraph-checkpoint 3.0.1 → 4.x
                                                        + langgraph-sdk + langgraph-prebuilt（传递）
```

pip 报错原文（可复跑）：

```
ERROR: Cannot install … (line 10) and langchain-core==0.3.86 because these package versions have conflicting dependencies.
    langgraph-prebuilt 1.0.13 depends on langchain-core>=1.3.1
    langgraph-checkpoint-sqlite 3.1.1 depends on langgraph-checkpoint<5.0.0 and >=4.1.0
    langgraph 1.0.1 depends on langgraph-checkpoint<4.0.0 and >=2.1.0
    langchain-openai 1.2.2 depends on openai<3.0.0 and >=2.26.0
```

---

## 已知风险点清单（Phase 2 从这张表开始查，⛔ 但以实测为准）

> ⚠️ **这张表是【假设】，不是结论。** 每条都标了"怎么证伪"。
> ⛔ **谁先坏、怎么坏，一律以 Task 4 跑出来的失败清单为准。**

| # | 位置 | 假设 | 怎么证伪 |
|---|---|---|---|
| **H1** 🔴 | `app/routing/api_v1_rag.py:966-1035` `get_agent_executor()` | `langchain.agents` 的 `create_tool_calling_agent` / `AgentExecutor` 是 **langchain 0.3 的 legacy agent API**；1.x 大概率**移除或搬家** | `grep -rn "get_agent_executor" app/tests/` 看有没有用例；再跑 `/ws/agent` 相关用例 |
| **H2** 🔴 | `app/rag/embedding_client.py:4` · `app/rag/query_rewriter.py:9` | `from openai import OpenAI` 在 **openai 2.x** 里可能改签名/行为 | 跑 `app/tests/` 里 embedding / query rewrite 那批 |
| **H3** | `app/core/llm_factory.py:146-160` | `ChatOpenAI(model=…, max_tokens=…, streaming=…)` 的参数在 1.x 有改名 | 读 `app/core/specs/llm_factory.md` 那条「**返回必须是裸 `ChatOpenAI`**」，再跑 `test_llm_factory*` |
| **H4** | `app/routing/api_v1_rag.py:1026-1031` | `ChatPromptTemplate` 的 `("placeholder", "{agent_scratchpad}")` 组合 | 同 H1 |
| **H5** | `app/agent/agent_checkpointer.py:6-7,208` · `agent_graph*.py` | `langgraph.graph.StateGraph/END` · `checkpoint.memory.MemorySaver` · `checkpoint.sqlite.SqliteSaver` 在 1.0.10 有改动 | 跑 `app/tests/test_approval_resume.py`（**真图**那批） |
| **H6** | `app/rag/chunker.py:5` | `langchain_text_splitters.RecursiveCharacterTextSplitter` 0.3→1.1 的默认参数变化（分块结果会变 ⇒ **会影响检索口径**） | 跑分块相关用例；⚠️ 若用例只测"能切"不测"切成什么"，**这条是假绿**，要手动核 |

---

## Phase 1 —— 只管"把真话说出来"

### Task 0：回滚快照（⛔ 不做这步不许动 venv）

**Files：**
- Create: `/Users/heweidong/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt`（**仓外**，同凭据目录，⛔ 不入库）

- [ ] **Step 1：给 venv 拍快照**

```bash
cd ~/Desktop/Product/agent-projects/projects/fastapi-rag-agent
./venv/bin/python -m pip freeze > ~/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt
wc -l ~/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt
```

预期：打印一个**大于 100** 的行数。若是 0 或很小 ⇒ **停下**，说明路径错了。

- [ ] **Step 2：确认它在仓外、且没被动跟踪**

```bash
git status --short          # ⇒ 应【没有】任何 "?? …凭据/…" 之类的输出
git check-ignore -v ~/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt || echo "⚠️ 不在任何 git 仓里（本就该如此）"
```

预期：`git status` 干净；第二条打印"不在任何 git 仓里"。

- [ ] **Step 3：记下回滚命令（写进本文件末尾，别只留在脑子里）**

```bash
# 回滚（只有在 Phase 2 收拾不了时才用）：
./venv/bin/python -m pip install -r ~/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt
```

- [ ] **Step 4：Commit** —— ⛔ **本 Task 不 commit**（只产出一个仓外文件，仓里没变化）

---

### Task 1：把目标版本组用 dry-run 定死

**Files：**
- 不落盘（探针）。产出 = **本文件下面这段要回填的版本表**

- [ ] **Step 1：解出目标组**

```bash
cd ~/Desktop/Product/agent-projects/projects/fastapi-rag-agent
TMP=$(mktemp)
grep -E '^[A-Za-z][^#]*==' app/requirements.txt > "$TMP"
python3 - "$TMP" <<'PY'
import sys,pathlib
p=pathlib.Path(sys.argv[1]); out=[]
skip={"langchain","langchain-core","langchain-community","langchain-openai",
      "langchain-text-splitters","langgraph","langgraph-checkpoint",
      "langgraph-checkpoint-sqlite","openai"}
for l in p.read_text().splitlines():
    if l.split('==')[0] in skip: continue
    out.append(l)
out += ["langchain>=1.0","langchain-core>=1.2.31","langchain-openai>=1.1.14",
        "langchain-text-splitters>=1.1.2","langgraph>=1.0.10",
        "langgraph-checkpoint>=4.1.1","langgraph-checkpoint-sqlite>=3.1.1","openai>=2.26.0"]
p.write_text("\n".join(out)+"\n")
PY
./venv/bin/python -m pip install --dry-run -r "$TMP" 2>&1 | grep -E "^Would install|ResolutionImpossible" | head -3
rm -f "$TMP"
```

- [ ] **Step 2：判过/不过**

- 输出 `Would install …` ⇒ **过**，把那一行**逐字抄进下方"目标版本组"**，进 Task 2。
- 输出 `ResolutionImpossible` ⇒ **不过** ⇒ ⛔ **停下**，把完整报错贴给业务方
  （这条链每退一层都可能再牵出新的包，比如 `openai` 就是这么浮出来的）。

- [ ] **Step 3：Commit** —— ⛔ **不 commit**（还没落盘任何东西）

**目标版本组（2026-10-09 实测回填 —— 逐字抄 `Would install`）：**

```
langchain-1.4.4  langchain-core-1.6.9  langchain-openai-1.7.0  langchain-text-splitters-1.1.3
langgraph-1.2.14  langgraph-checkpoint-4.2.0  langgraph-checkpoint-sqlite-3.1.1
langgraph-prebuilt-1.1.0  langgraph-sdk-0.4.6  openai-2.54.0
```

⚠️ **两件查实的事**（都写进 `DEC-127`）：

1. 🔴 **Security 表里那几个「修好于」版本【互相不成组】** —— 它们是各自的下界，不是一套协调的版本。
   实测：`langchain==1.3.9` 要 `langchain-core>=1.4.6`；`langchain 1.3.10+` 又要 `langgraph>=1.2.5`；
   `1.3.16+` 要 `core>=1.6.0`。⇒ **"取最小修复版"这条路走不通**，只能让 resolver 挑一套后再就地钉。
2. 🔴 **`openai` 不是可选项**：`langchain-openai 1.x` 硬要 `openai>=2.26.0,<3.0.0`，
   而 `ChatOpenAI` 是 `llm_factory` 的底座 ⇒ **必须升**。⚠️ 而本仓**直接**用它
   （`app/rag/embedding_client.py:4` · `app/rag/query_rewriter.py:9`）⇒ 落在 **RAG 主路径**上。
   ⇒ **业务方 2026-10-09 裁：夹在 2.x（`openai==2.54.0`），⛔ 不跟 resolver 默认的 3.27.0** ——
   理由：本仓取向是「**只做必要的**」，没有任何东西要求 3.x，而它跨**两个**大版本（1→3）而非一个（1→2）。

---

### Task 2：改 `app/requirements.txt`（只改那几行）

**Files：**
- Modify: `app/requirements.txt`（langchain / langchain-core / langchain-openai /
  langchain-text-splitters / langgraph / langgraph-checkpoint /
  langgraph-checkpoint-sqlite / openai，共 8 行）
- ⚠️ **`langchain-community` 单独处理** —— 它**全仓没有任何 import**
  （`grep -rn --include='*.py' 'langchain_community' app/` ⇒ 空）⇒ **删不删要单独裁，本 Task ⛔ 不动它**

- [ ] **Step 1：逐行改（每行都补一行注释说明"为什么动它"）**

改法形如（⛔ 版本号以 Task 1 回填的那张表为准）：

```text
openai==2.26.0      # ← 2026-10-09 大版本跳（原 1.109.1）· langchain-openai 1.x 硬要 >=2.26.0,<3.0.0
                    #    ⚠️ 本仓【直接】用它：app/rag/embedding_client.py · app/rag/query_rewriter.py
```

- [ ] **Step 2：核那三条判据（本仓 §3.3 的口径）**

```bash
grep -cE '^[A-Za-z][^#]*==' app/requirements.txt   # ⇒ 40（行数不许变）
grep -cE '^[A-Za-z][^#]*>=' app/requirements.txt   # ⇒ 6
grep -vE '^\s*(#|$)' app/requirements.txt | grep -cvE '^[A-Za-z][^#]*(==|>=)'   # ⇒ 0（无裸名）
```

- [ ] **Step 3：Commit**

```bash
git add app/requirements.txt
git commit -m "chore(deps): 钉死行改到 langchain-core 1.x 组（含 openai 2.x）—— 先改声明，装完再修代码"
```

⚠️ **Commit message 里必须写**：「**本次无决策事项** —— 目标版本组由 Task 1 的 dry-run 实测决定」
（若 `langchain-community` 的去留被问到 ⇒ 那是决策，要单独建 DEC）。

---

### Task 3：装进 venv

**Files：** 无（改本机环境）

- [ ] **Step 1：装**

```bash
cd ~/Desktop/Product/agent-projects/projects/fastapi-rag-agent
TMP=$(mktemp)
grep -E '^[A-Za-z][^#]*==' app/requirements.txt > "$TMP"     # 只喂钉死集（6 个 >= 的包不在本机）
./venv/bin/python -m pip install -r "$TMP" 2>&1 | tail -5
rm -f "$TMP"
```

- [ ] **Step 2：核装上了什么（⛔ 别信 pip 的"Successfully"）**

```bash
./venv/bin/python -m pip list 2>/dev/null | grep -iE '^(langchain|langgraph|openai|langchain-core|langchain-openai|langchain-text-splitters)'
./venv/bin/python -c "import langchain_core, langgraph, openai; print(langchain_core.__version__, openai.__version__)"
```

- [ ] **Step 3：Commit** —— ⛔ **不 commit**（venv 不在库里）

---

### Task 4：🔴 **相变门 —— 采集真实失败清单，然后停下来重新规划**

**Files：**
- Modify: 本文件（把失败清单**逐字**回填进下方）

- [ ] **Step 1：跑全量离线测试，把失败**逐条**记下来**

```bash
cd ~/Desktop/Product/agent-projects/projects/fastapi-rag-agent
./venv/bin/python -m pytest app/ -m "not integration and not needs_db" -q 2>&1 | tail -40
```

- [ ] **Step 2：把结果分成三类，写进下方表格**

| 类别 | 含义 | 处理 |
|---|---|---|
| **A · 收集期错** | `ImportError` / `AttributeError`（模块或符号没了） | Phase 2 的首要任务 |
| **B · 断言变了** | 能跑，但结果不同（分块数变了 / 消息结构变了） | 要判：**是新版本对，还是我们错了** |
| **C · 真服务才露的** | 离线全绿也要记 | 留到 Phase 2 末尾的真服务验 |

- [ ] **Step 3：判「基线是否仍成立」**

- `913 passed / 2 skipped` ⇒ 🎉 **Phase 2 缩成"只做真服务验 + 文档"**
- 有任何红 ⇒ **把上面那张表贴给业务方，重新规划 Phase 2**（⛔ 别自己闷头改）

- [ ] **Step 4：Commit**

```bash
git add fastapi-rag-agent-TODO待办/施工单-20261009-langchain-core-1x连锁升级.md
git commit -m "docs(deps): 落 langchain-core 1.x 升级的实测失败清单（Phase 1 出口）"
```

**失败清单（2026-10-09 实测回填）：**

```
913 passed, 2 skipped, 48 deselected, 23 warnings in 56.35s      ← ⚠️ 与基线【一模一样】⇒ 见下方警告
```

> ## 🔴🔴 这条「全绿」是【假绿】—— 本轮最该记住的一件
>
> 基线没动**不是因为没事**，是因为 **913 条里没有一条碰过那个坏掉的东西**。
> **判据（可打印）**：直接调真身 ⇒
>
> ```
> 🔴 真身起不来 ⇒ ImportError: cannot import name 'create_tool_calling_agent'
>                 from 'langchain.agents'
> ```
>
> 而那两条**唯一提到它**的用例（`app/tests/test_ws_auth.py:292` · `:376`）
> **`monkeypatch.setattr(api_v1_rag, "get_agent_executor", …)` 把它整个换掉了**
> ⇒ **函数体从没被执行** ⇒ `ImportError` 永远碰不到。
> ⚠️ **这不是那两条用例写错了** —— 它们测的是"**鉴权之前端点体不许跑**"，替换掉是对的。
> 错的是**把「913 全绿」读成「升级没坏东西」**。

| 类别 | 条数 | 内容 |
|---|---|---|
| **A · 收集期错** | **1** | `app/routing/api_v1_rag.py:971` —— `from langchain.agents import create_tool_calling_agent, AgentExecutor` ⇒ **两个符号在 langchain 1.x 里都没了**。影响：**`/ws/agent` 整条活路径起不来**（它是 live path，`api_v1_rag.py:1097` 真调） |
| **B · 断言变了** | **0** | 913 passed / 2 skipped，与基线逐字一致 |
| **C · 真服务才露的** | **待测** | 见 Phase 2 末尾 |

**其余 5 个假设的核实结果（都是「没坏」，但都验过了，⛔ 不是推断）：**

| 假设 | 核实方式 | 结果 |
|---|---|---|
| **H2** `openai` 2.x | 逐符号 import + 两个模块真导入 | ✅ `from openai import OpenAI` 可用 |
| **H3** `ChatOpenAI` 参数 | **调真身** `make_llm("chat","answer")` | ✅ 仍是**裸 `ChatOpenAI`**（spec 那条硬约束保住）· `model_name=deepseek-v4-flash` · `max_tokens=2000` · `streaming=False` |
| **H4** agent_scratchpad | 随 H1 一起（同一段代码） | ⏸ 等 H1 修完再验 |
| **H5** langgraph | 17 个符号逐个 import + **真起 SqliteSaver** | ✅ `StateGraph` / `END` / `MemorySaver` / `SqliteSaver` 全在、可用 |
| **H6** 分块参数 | 读 `app/rag/chunker.py:46-49` | ✅ **显式传参**（`chunk_size` / `chunk_overlap` / `separators`）⇒ 不吃默认值 |
| **全模块扫描** | 62 个产品模块逐个 import | ✅ **0 个导入期失败**（`alembic.*` 那 4 条是扫描脚本自己的遮蔽伪影，⛔ 不是真坏） |

---

## Phase 2 —— ✅ **已完成**（2026-10-09 当天做完）

> 原计划这里**刻意留白**、写"由 Phase 1 的实测驱动，⛔ 不许凭空写"。
> **实测只坏了一处**（H1），修法也清楚 ⇒ 当天做完，本文件续写如下。

### Task 5：修 H1 —— `/ws/agent` 的 legacy agent API 没了

**Files：**
- Modify: `app/routing/api_v1_rag.py`（`get_agent_executor()` 里**那一行 import**）
- Modify: `app/requirements.txt`（🆕 加 `langchain-classic==1.0.8`）
- Create: `docs/decisions/DEC-127-langchain-core-1x连锁升级.md`
- Modify: `scripts/check_dep_vulns.sh`（⚠️ 不在原计划里，见下）

- [x] **Step 1：先验 `langchain-classic` 值不值得加** —— ✅ 实测三条：
  它只要求 `langchain-core<2.0.0,>=1.4.4`（我们装 1.6.9 ✅）·
  `langchain-community` 在它那里**只是 extra，⛔ 不是硬依赖** ·
  加进钉死集后**整个解析结果零变化**（`Would install langchain-classic-1.0.8`）
- [x] **Step 2：改那一行** —— `from langchain.agents import …` ⇒ `from langchain_classic.agents import …`
  （**实现一行没动**）
- [x] **Step 3：🔴 验【真身】—— 这就是本 Task 的判据，⛔ 别用 `pytest` 当它**

```bash
./venv/bin/python -c "import sys;sys.path.insert(0,'app');import routing.api_v1_rag as m;print(m.get_agent_executor(), [t.name for t in m.get_agent_executor().tools])"
```
  预期：不抛错 · 打出一个 `AgentExecutor` · 工具 = `['calculator', 'date_today', 'web_search']`
- [x] **Step 4：全量** —— `pytest app/ -m "not integration and not needs_db" -q` ⇒ **913 passed / 2 skipped** ·
  `bash scripts/ci-local.sh` ⇒ **退出码 0**
- [x] **Step 5：复扫依赖** —— `bash scripts/check_dep_vulns.sh` ⇒ **退出码 0** +「扫了 165 个包，**0 条**」
- [x] **Step 6：Commit**

### Task 6：⚠️ **顺手修的一处，不在原计划里** —— `check_dep_vulns.sh` 自己会撒谎

**发现方式**：Step 5 复扫时它**崩了** —— `pypi.org` 读超时 ⇒ `requests.exceptions.ReadTimeout`
⇒ 而它**输出了「🔴 有已知漏洞」**，退出码 1。

**根因**：`pip-audit` 的「**找到漏洞**」退出码是 **1**，而 **Python 未捕获异常的退出码也是 1**
⇒ 脚本只看退出码 ⇒ **网络崩了被报成"有漏洞"**。
⚠️ **同族**：本仓 `docs/复盘/2026-10-05-拿代理量当判据.md`（两个状况共用一个信号）。

**修法**：改成**按「输出是不是合法 JSON」判**（`--format json`），退出码**只用于打印**。
自测从 **1 相扩到 3 相**：真跑到漏洞（⇒1）· **喂垃圾（⇒2，"判不了"）** · 喂干净 JSON（⇒0）。

- [x] **Step 1：改判定** · **Step 2：扩自测到三相** · **Step 3：跑 `--self-test`** ⇒ 三相全过 · **Step 4：Commit**

⚠️ **顺带自己踩了一个坑并修掉**：改这个脚本时，我在**双引号字符串里写了反引号**
⇒ shell 把 `` `pip-audit` `` **当命令执行了**（`line 189: pip-audit: command not found`）。
**同族**：记忆里那条 `backtick-in-unquoted-heredoc-executes`。已改成不带反引号，
并加了机械扫描：`grep -nE '^\s*[^#]*"[^"]*`' scripts/check_dep_vulns.sh` ⇒ 空。

---

## ⚠️ 本文件【还没做】的那一件

**真服务验证**（`DEC-127` §五·5）—— 改的是 LLM 调用链，而本仓「测试全过」⛔ **不算**这条的凭证。
待验三条：`/ws/agent` 端到端 · `/rag/*` 的 embedding 与查询改写（`openai` 2.x）· **记账金额正确**。

---

## 回滚

```bash
# 只有在 Phase 2 收拾不了时才用（把 venv 整回 Task 0 那一刻）
cd ~/Desktop/Product/agent-projects/projects/fastapi-rag-agent
./venv/bin/python -m pip install -r ~/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt
git checkout main && git branch -D fix/dep-upgrade-batch1   # ⚠️ 只有确实要放弃这条分支时才做
```

⚠️ **未推送的东西先推**（本仓「当天结束前至少推一次」）。
