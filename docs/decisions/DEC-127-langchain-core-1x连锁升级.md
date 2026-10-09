# DEC-127 · `langchain-core` 0.3 → 1.x 连锁升级（含 `openai` 钉 2.x 而非 3.x）

| 项 | 内容 |
|---|---|
| **状态** | ✅ **已落**（2026-10-09 · 分支 `fix/dep-upgrade-batch1`） |
| **触发** | 业务方 2026-10-09 裁「**§3.4 甲 · 完整修好**」+「**能修的全部处理好，不要直接留尾巴**」 |
| **类型** | **依赖大版本连锁升级**（⛔ 不是新功能） |
| **落点** | `app/requirements.txt` 的 8 行 · 本条 DEC · 施工单 `施工单-20261009-langchain-core-1x连锁升级.md` |
| **关联** | `SECURITY.md` **§3.4**（依赖闭包，权威）· `DEC-034`（不另建约束文件）· `DEC-039`（推送节奏） |

---

## 一 · 要解决的是什么

`SECURITY.md` §3.4 的 19 条已知漏洞里，**17 条**挂在 langchain/langgraph 全家桶上。
原计划分「小版本批 / 大版本批」两批做 ⇒ **2026-10-09 实测推翻**：

```
langchain-core  0.3.86 → >=1.2.31          ← 总闸
   ├─ 逼 langchain                0.3.30  → 1.x
   ├─ 逼 langchain-openai         0.2.14  → 1.x  ⇒ 🔴 再逼 openai 1.109.1 → >=2.26.0
   ├─ 逼 langchain-text-splitters 0.3.11  → 1.1.x
   └─ 逼 langgraph                1.0.1   → 1.2.x ⇒ 连带 langgraph-checkpoint 3.x → 4.x
```

⇒ **除 `pyjwt`（已于同日单独升到 2.15.0）外，剩下 8 个包是【一件事】。**

---

## 二 · 决策点

### 2.1 🔴 `openai` 钉 **2.54.0** 还是 **3.27.0**（**这是本 DEC 存在的唯一理由**）

**背景**：`langchain-openai 1.x` 硬要 `openai>=2.26.0,<3.0.0` ⇒ **`openai` 必须升，不是可选项**。
⚠️ 而本仓**直接**用它（不是只走 langchain）：
`app/rag/embedding_client.py:4` · `app/rag/query_rewriter.py:9` ⇒ **落在 RAG 主路径上**。

| 备选 | 结果 | 判断 |
|---|---|---|
| **甲（选）：夹在 2.x ⇒ `openai==2.54.0`** | 跨度 **1.109.1 → 2.x**（一个大版本） | ✅ **选** |
| 乙：跟 resolver 默认 ⇒ `openai==3.27.0` | 跨度 **1.109.1 → 3.x**（**两个**大版本） | ⛔ 不选 |

**选甲的理由**（业务方 2026-10-09 当面裁）：

1. **本仓的取向是「只做必要的」，不是「用最新的」。** 目标是把 §3.4 的漏洞清掉 ——
   `openai 2.54.0` 就清得掉（实测复扫确认），**没有任何东西要求 3.x**。
2. **`langchain-openai 1.7.0` 两者都收** ⇒ 夹 2.x **不引入任何新约束，只是把钉的版本选低一档**。
3. **改动的面越小，越可能一次做对** —— 而这一层偏偏落在 **RAG 主路径**上。
   ⚠️ 本仓对"改完没真验过"有明确事故记录（单测 21 条全绿而真服务 500）。

**⚠️ 不是选甲的理由**（⛔ 别记歪）：不是因为 3.x 有已知漏洞。**没有查到这种说法。**

### 2.2 ⚠️ 「取 Security 表里那几个『修好于』版本」这条路**走不通**（查实，不是选择）

**实测**：那几个版本**互相不成组** —— 它们是**各自的下界**，不是一套协调的版本。
`langchain==1.3.9` 要 `langchain-core>=1.4.6`；`langchain 1.3.10+` 又要 `langgraph>=1.2.5`；
`1.3.16+` 要 `core>=1.6.0`。⇒ 试了 4 种「贴近最小」的组合，**全部 `ResolutionImpossible`**。

⇒ **做法只能是**：让 resolver 挑一套自洽的，**装完再就地钉死**（与 §3.3 同一个手法）。
📌 **反过来说**：`SECURITY.md` §3.4 那张表的「修好于」列，**只能当下界读，⛔ 不能当升级目标读**。
—— 这一条已写进 §3.4。

### 2.3 ⛔ **未裁**：`langchain-community` 去留（本 DEC 不处理）

查实：**全仓没有任何 import** —— `grep -rn --include='*.py' 'langchain_community' app/` ⇒ **空**。
它现在纯挂名（钉在 `0.3.31`）。⚠️ **删不删是另一件事，⛔ 本 DEC 不动它**
（删依赖要单独看它是不是被传递依赖需要）。已记进施工单。

### 2.4 🔴 `/ws/agent` 那条坏掉的活路径怎么修 —— 加 `langchain-classic`

**背景**：升级后 `app/routing/api_v1_rag.py` 的 `get_agent_executor()` **整个起不来** ——
`langchain.agents` 里 `create_tool_calling_agent` / `AgentExecutor` **两个符号都没了**。
⚠️ **而 913 条测试全绿**（唯一提到它的两条用例把它 `monkeypatch` 掉了）⇒ **假绿**。

| 备选 | 判断 |
|---|---|
| **甲（选）：加 `langchain-classic==1.0.8`，只改那一行 import** | ✅ **选** |
| 乙：换成 `langchain 1.x` 的 `create_agent(...)` | ⛔ 不选，见下 |
| 丙：照 `app/agent/agent_graph.py` 的先例，自己用 langgraph 手搓一份等价的 | ⛔ 不选 —— **代码最多、可坏面最大**，且等于把"升依赖"改成"重写功能" |

**选甲的理由**（业务方 2026-10-09 当面裁）：

1. **这一轮的目标是「把漏洞清掉」，⛔ 不是「换 API」。** 甲**实现一行没动** ——
   同一份代码，只是从 `langchain.agents` 搬到了 `langchain_classic.agents`（**官方指定的家**）。
2. **乙会改行为，而回调和记账正挂在上面**：`AgentExecutor.ainvoke(...)` 的输入键是 `"input"`、
   输出键是 `"output"`；`create_agent` 返回的是 **langgraph 的 `CompiledStateGraph`**，
   输入输出都变成 `{"messages": [...]}` ⇒ 要写适配层，而且 `on_agent_finish` **不再触发**
   （`api_v1_rag.py` 里那段兜底会接管，但那是**另一条路径**了）。
   🔴 更关键：本端点的记账走 `WebSocketAgentCallback.on_llm_end`，而 `DEC-075` 的**身份传递**就挂在那里
   ⇒ **换 API 有把记账弄歪的风险**，而本仓对记账写歪有明确的付费前科。
3. **甲的成本已实测到底**：`langchain-classic 1.0.8` 只要求 `langchain-core<2.0.0,>=1.4.4`（我们装了 1.6.9 ✅）·
   `langchain-community` 在它那里**只是 extra（⛔ 不是硬依赖）** · 加进钉死集后**解析结果零变化**。

**⚠️ 甲的代价（诚实记）**：`langchain-classic` 是**官方标注的 legacy 包**。
**到期日**是"它哪天不再跟随 `langchain-core` 发版"—— 那是个**有明确信号的未来问题**，
届时按乙重做。本 DEC 的结论**不是"甲永远对"，是"现在这轮甲对"**。

---

## 三 · 落地了什么

| | |
|---|---|
| **改了 8 行 + 加 1 行**（`app/requirements.txt`） | `langchain 0.3.30→1.4.4` · `langchain-core 0.3.86→1.6.9` · `langchain-openai 0.2.14→1.7.0` · `langchain-text-splitters 0.3.11→1.1.3` · `langgraph 1.0.1→1.2.14` · `langgraph-checkpoint 3.0.1→4.2.0` · `langgraph-checkpoint-sqlite 3.0.3→3.1.1` · **`openai 1.109.1→2.54.0`** · 🆕 **`langchain-classic==1.0.8`**（§2.4） |
| **代码改了 1 行** | `app/routing/api_v1_rag.py` —— `from langchain.agents import …` ⇒ `from langchain_classic.agents import …`（**实现一行没动**） |
| **包行数** | **47 个包行 = 41 个 `==` + 6 个 `>=` + 0 个裸名**（那 6 个不在本机 venv、取不到实测版本，见 §3.3） |
| **`langgraph-prebuilt` / `langgraph-sdk`** | ⚠️ **不在 `requirements.txt` 里**（是 `langgraph` 的传递依赖）⇒ **仍未裁要不要补进去** |
| 🔴 **副作用：修掉了一个【门自己会撒谎】的 bug** | `scripts/check_dep_vulns.sh` 原先**只看 `pip-audit` 的退出码** ⇒ 而「**找到漏洞**」与「**Python 抛异常（网络超时）**」**退出码都是 1** ⇒ **网络崩了被报成「有已知漏洞」**。已改成**按「输出是不是合法 JSON」判**，三态自测从 1 相扩到 **3 相**（含"判不了必须落 2"那一相） |

---

## 四 · 反悔成本

| 反悔 | 成本 |
|---|---|
| **甲 → 乙**（`openai` 2.x 改 3.x） | **低** —— 改一行 + 重装 + 重跑 913 条。而且要等 `langchain-openai` 哪天不再收 2.x 时**本来就必须做** |
| **乙 → 甲**（3.x 退回 2.x） | **低** —— 同上 |
| **整轮退回** | **低** —— 快照在仓外：`~/Desktop/Product-external/fastapi-rag-agent-凭据/venv-freeze-20261009-pre-langchain1x.txt`（195 行） |

⇒ **这条选择是【可逆的、低成本的】** —— 所以不必为它纠结太久；真正难的是配套的代码改动（见施工单）。

---

## 五 · 遗留

1. ✅ **`/ws/agent` 已修**（§2.4）—— 判据：
   `./venv/bin/python -c "import sys;sys.path.insert(0,'app');import routing.api_v1_rag as m;m.get_agent_executor()"`
   ⇒ **不抛 ImportError**，且建出来的 `AgentExecutor` 带 `['calculator','date_today','web_search']` 三个工具。
2. ⛔ **`langchain-community` 去留**（§2.3）—— 它现在**仍然没被任何代码 import**。
3. ⛔ **要不要把 `langgraph-sdk` / `langgraph-prebuilt` 补进 `requirements.txt`**（§三）
4. ✅ **依赖漏洞已清零** —— 2026-10-09 实测 `bash scripts/check_dep_vulns.sh` ⇒
   **`（扫了 165 个包，0 条）` + 退出码 0**。§3.4 那 19 条 **全部清掉**（`pyjwt` 那 2 条已于同日单独清）。
5. ✅ **真服务验证【已做】**（2026-10-09，起真服务 + 真调 LLM）—— 三条全过：

| 验什么 | 怎么验 | 结果 |
|---|---|---|
| **`/ws/agent` 端到端**（**就是那条修过的活路径**） | WS 连 `/api/v1/ws/agent`，首帧 `{"type":"auth","api_key":…}` | ✅ 回 `{"type":"ready"}` ⇒ 发问题 ⇒ **thinking → final（"3 加 5 等于 8。"）→ done**，**3 帧、无 error** |
| **`/rag/*` 的 embedding + 查询改写**（`openai` 2.x 直接落点） | `POST /api/v1/rag/search?mode=accurate_norerank` | ✅ **HTTP 200**；`rewrite_enabled=True` · **`rewrite_ms=3726`**（真调了 LLM）· `bm25_enabled=True` · **命中 3 条**且是正确语料 |
| **记账金额** | `GET /api/v1/agent/token/usage` | ✅ `{"user_name":"…","summary":{"total_tokens":906,"total_cost":0.001913,"calls":2}}` —— **账记到了认证出来的人头上**，且 `calls` 与实调次数对得上 |

   ⚠️ **一条别误读**：用**新用户**搜时命中 **0 条** —— ✅ 那是**按 `requested_by` 过滤的正确隔离行为**
   （`app/rag/bm25_index.py:65`），⛔ **不是**检索坏了。**正控**：拿 `isolation_a`（自己名下有 6 篇）
   再搜 ⇒ **命中 3 条**。📌 **"0 条"必须配上正控才算验过**。

6. 🔴 **`#123` 模块化重构【顺带打断的两个活工具】—— 本轮一并修了**
   （📄 复盘 ⇒ `docs/复盘/2026-10-09-测试全绿而活路径坏了两次.md`）：
   `scripts/issue_api_key.py`（`from auth import` · `from db import`）·
   `scripts/check_corpus_dedup.py`（`API_DIR = REPO_ROOT / "api"` + `from chunker import`）。
   ⚠️ **两处 913 条测试都照不到**（脚本不在 pytest 采集范围；`compileall` 只查语法，
   而这是**导入期**错）⇒ ⛔ **别把这一条读成本次依赖升级的锅**，它是**当天另一个改动**留下的。
