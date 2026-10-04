# `api/agent_graph_advanced_learning.py`

> 🆕 **本 spec 建于 2026-10-04** —— 此前本模块**没有 spec**（`bash scripts/spec_status.sh --missing` 里一直有它）。
> 建它的直接起因：`B1` 剩余 4 条链要做真流式，而**「这条链里哪些节点该流、哪些绝不能流」这个判断
> 只存在于本模块内部**（⛔ 读代码推不出来 —— 见下方 ⭐ 节的表）。

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用，且是生产链** —— 但 🔴 **它对 LLM 的花销【一处都不记账】**，且 ⚠️ **两个分支本来就无字可流**（见下）<br>🔵 **2026-10-04（`B1` 剩余 4 条链）：4 个该流的节点改成【真流式】** —— `search_summarize`（`:133`）· `translate_execute`（`:203`）· `agent_decide`（`:235`）· `chat_node`（`:385`）都声明 `config: RunnableConfig` + 换 `.stream(…, config=config)` 逐块 `+` 聚合 ⇒ **本图 388 → 450 行**（多出的行是"为什么这 4 个流、那 2 个不流"的注释 + 白名单常量 + 每个节点的改法说明）。<br>⚠️ **本图 4 个节点【全是同步的】** ⇒ 走**同步** `.stream(config=config)`；⛔ **别照抄链 C**（`agent_graph_advanced.py` 那两个是 `async` ⇒ 用 `astream`），⛔ **也别把本图节点改成 `async def`** —— 同步的 `graph.invoke()` 会当场 `TypeError: No synchronous function provided to "agent"`（`DEC-050` 实测）。<br>新增模块级 `STREAMABLE_NODES`（`:339`）；**为什么必须放模块级**（放进 `build_advanced_agent()` 就是局部名 ⇒ 端点 `AttributeError`）写在 `:316-338` 的注释里。<br>🔴 **链 A 走 `astream` 时必须开 `subgraphs=True`** —— 本图 5 个子图，**不开它一个字都流不出来**（⚠️ 且 `meta["langgraph_node"]` 报的是**子图内层**名，见 ⚠️④）。⚠️ **`+` 聚合在本图同样【必须】**：`tool_calls` 碎片化到达，只拼 `content` ⇒ react 子图拿不到 `tool_calls` ⇒ **工具永远不执行**，而接口一切正常。<br>📌 守卫 `api/test_agent_stream_chains.py`（含 `test_real_chain_a_node_streams_one_chunk_per_token` · `test_chain_a_filters_out_supervisor_and_calc_execute`） |
| **对外提供** | `build_advanced_agent()`（`:349`，返回**编译好的图**，带 `MemorySaver`）<br>· 5 个 `create_*_subgraph()`（`:120` / `:160` / `:180` / `:196` / `:223`）<br>· 模块级 `llm`（`:22`）· `llm_search`（`:81`）· `llm_calc`（`:82`）· `llm_date`（`:83`）· `llm_with_tools`（`:75`）<br>· 工具 `calculator`（`:26`）· `date_today`（`:32`）· `tools`（`:60`，**从 `mcp_server.TOOLS` 派生**）<br>· `inject_memories_to_prompt()`（`:97`）· `AgentState`（`:86`）· 🆕 `STREAMABLE_NODES`（`:339`） |
| **谁在用** | `api_v1_agent.py:34` import → `:430` **模块级建图**（`advanced_agent = build_advanced_agent()`）→ `POST /agent/advanced_chat`（`:434` 定义 · `:455` `advanced_agent.invoke(...)`）<br>🆕 **`POST /agent/advanced_chat/stream`**（`:474`，`B1` · 2026-10-04）—— 同一张图，走 `astream(..., subgraphs=True)`（`:535`），汇总取自 `aget_state`（`:524`） |
| **规模** | **450 行**（`bash scripts/spec_status.sh` 的口径 = 真实行数；⚠️ 本文件用 `wc -l` 会得 449 —— **末行没有换行符**，⛔ 差 1 不是笔误） |

## ✅ 做了什么

- **一张「主管路由 + 5 个部门子图」的图**（`build_advanced_agent`，`:349`）：
  `supervisor`（`:353`，判意图）→ `route_by_intent`（`:423`）→ 六选一 →
  `search_dept` / `calc_dept` / `date_dept` / `translate_dept` / `react_dept` / `chat` → `END`
- **5 个子图各自独立编译**（`:157` / `:177` / `:192` / `:218` / `:314`）：搜索（2 节点）· 计算（1）· 日期（1）· 翻译（1）· **ReAct（3 节点 + 循环）**
- **长期记忆注入**：`supervisor`（`:363`）与 `inject_memories_to_prompt`（`:107`）都查 mem0；
  `user_id = f"{user_name}:{memory_space}"`（`:361` / `:106`）
- **工具表从 MCP 注册表派生**（`:58-60`）—— **单一事实源**（2026-09-20 业务方裁「乙」；理由与实测见 `:38-56`）
- **REACT 子图有收尾节点**（`summarize`，`:285`）—— 2026-09-20 补的，此前 `final_output` 永远留占位串
- **`calculator` 走 `safe_math.calculate`**（`:26`）—— `DEC-049`，⛔ 不许改回 `eval`
- 🔵 **真流式（`B1` · 2026-10-04）**：4 个节点（`:133` / `:203` / `:235` / `:385`）声明 `config: RunnableConfig`
  并用 `.stream(…, config=config)` 逐块聚合 ⇒ `/agent/advanced_chat/stream` 的
  `astream(…, subgraphs=True)` 才拿得到 **token 级**的块。📄 裁定 ⇒ `DEC-050` · 白名单 ⇒ `STREAMABLE_NODES`（`:339`）
  ⚠️ **节点保持同步** —— 改 `async def` 会当场 `TypeError`（见状态栏）

## 🟡 做到哪 / 缺什么

- 🔴 **本模块的 LLM 调用【一处都不记账】**
  —— 判据（可打印）：`grep -c record_usage api/agent_graph_advanced_learning.py` ⇒ **0**。
  而它**每次请求至少真跑 1 次 LLM**（`supervisor`），走 REACT 还要多轮
  ⇒ **`/agent/advanced_chat` 的花销在 `token_usage_logs` 里看不见**，看板（`B13`/`R4`）上的钱偏少。
  📌 **同族**：`api/api_v1_rag.py` 也是 0（那个已在它的 spec 里登记）。
  ⚠️ **端点上那两道闸**（`check_session_token_budget` / `circuit(global_key())`，`api_v1_agent.py:469/475`）
  **只是"拦"，不是"记"** —— 别把两者读成一回事。
- ⚠️ **`MemorySaver()`**（`:450`）是**进程内存** ⇒ 重启即丢（与 `/agent/langgraph_chat`·`/agent/mcp_chat` 同）。
- ⚠️ **`calculator` / `date_today` 在本文件里是【第二份定义】**（`:26` / `:32`）——
  与 `mcp_server.TOOLS` 里那两个**同名、不同对象**（被**子图节点直接 `.invoke()`**：`:170` / `:185`）。
  实现逐字等价、**当前无害**，但属"重复定义"（`:70-72` 自己记了这笔账，登记为清理项）。
- ⚠️ **`supervisor` 直接改 `state` 再整个返回**（`:381-382`）——
  与本仓别处的 `return {...}` 风格不同，读的时候容易看漏它**确实**写了 `intent`。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **① 这是"进阶示例"** | ⛔ **它是 `POST /agent/advanced_chat` 的图本体** —— 模块 docstring 第 1 行写着「LangGraph **进阶示例**」。<br>**判据**：看谁 import 它（`api_v1_agent.py:34`）⇒ 名字与自述都不可信（同 `agent_graph_advanced.py` 的 ⚠️①）。 |
| 🔴 **② 「调 LLM 的节点都能流」** | ⛔ **6 个调 LLM 的节点里只有 4 个该流** —— 见下表。**这张表就是本 spec 存在的理由**：<br>它**⛔ 读代码推不出来**（要同时知道「这个节点的 LLM 输出是什么角色」+「答案最终从哪来」）。 |
| ⚠️ **③ 「流式失败 ⇒ 一个字都流不出来」** | ⛔ **反了**：`calc_dept` / `date_dept` **两条分支本来就无字可流** —— 它们的答案来自**工具返回值**，不来自 LLM。<br>⇒ 用户会**一直等到最后一帧**才看到 `answer`。**这是设计如此，⛔ 不是 bug。** |
| ⚠️ **④ 子图节点的名字** | **父图里**它们叫 `search_dept` / `react_dept`…，而 `stream_mode="messages"` 的 `meta["langgraph_node"]`<br>报的是**子图内层**名（`search_summarize` / `agent`…）—— ⚠️ **前提是开了 `subgraphs=True`**；<br>不开，要么只拿到子图的**返回值**（1 块整段 · 外层名），要么**一块都没有**。<br>📄 实测六剧本表 ⇒ `fastapi-rag-agent-TODO待办/探针-真流式与子图.py` · 勘察 §8.3 |
| ⚠️ **⑤ `should_continue` 是本仓唯一那个** | ⛔ **不是** —— 本文件 `:278` 那个是**局部函数**，返回 **`"tools"` / `END`**；<br>`agent_graph.py:195` 那个返回 **`"approval"` / `"tools"` / END**；`agent_graph_advanced.py:430` 那个返回 **`"tools"` / `"chat"`**。<br>**同名 · 三个语义 · 三个作用域。** |
| ⚠️ **⑥ 路由是"容错"的** | ⛔ **是【精确匹配】的**（`:423-430`）：`intent.content.strip()` 与 `"SEARCH"` 等**逐字相等**才命中，<br>**否则一律落 `chat`**（兜底）。⇒ 模型多吐一个句号（`REACT。`）就**静默走错分支**、且**不报错**。<br>⚠️ 这是**真实风险**，不是理论 —— 提示词（`:370`）只写「只返回一个单词」，**没有输出约束**。<br>🔵 **`B1` 之后这条更值得注意**：`chat_node` 是兜底 ⇒ **大多数请求走的其实是这条分支**（其 docstring `:385-390` 已写明） |

### 🔴 ⭐ 节点表：**6 个调 LLM 的节点，只有 4 个该流**

| 节点 | 行（`def`） | 调什么 LLM | 该流？ | 为什么 |
|---|---|---|---|---|
| `supervisor` | `:353` | `llm.invoke(classify_prompt)`（`:380`） | ❌ | 输出是**路由词** `SEARCH`/`CALCULATOR`/… —— 流给用户 = 答案前面先蹦一个 `SEARCH` |
| `chat_node` | `:385` | `llm.invoke(messages)` → 🔵 **`.stream(…, config=config)`**（`:400`） | ✅ | 就是答案。⚠️ **它是兜底分支** ⇒ 大多数请求走这条 |
| `search_summarize` | `:133` | `llm_search.invoke(…)` → 🔵 **`.stream(…, config=config)`**（`:147`） | ✅ | 一句话总结 = 答案 |
| `calc_execute` | `:164` | `llm_calc.invoke(extract_prompt)`（`:169`） | ❌ | **只提取表达式**（`6*7`）；真答案 `42` 来自 `calculator` 工具（`:170`），**⛔ 不是 LLM 输出** |
| `translate_execute` | `:203` | `llm.invoke(prompt)` → 🔵 **`.stream(…, config=config)`**（`:210`） | ✅ | 译文 = 答案 |
| `agent`（REACT 子图） | `:235` | `llm_react_with_tools.invoke(messages)` → 🔵 **`.stream(…, config=config)`**（`:251`） | ✅ | 答案 + `tool_calls` |

另有 **2 个节点不调 LLM**（**本来就无字可流**）：`date_execute`（`:184`，纯工具）、
`summarize`（`:285`，只把最后一条消息的 `content` 搬进 `final_output`）。

⚠️ **行号口径**：本表为 **2026-10-04 批 4 之后**的实测值（`grep -n "def <节点名>"` 可复核）。
⛔ **别拿本文档早先版本的旧行号去找** —— 每个被改的节点都加了说明注释，**且各节点下移量不同**（+3 ~ +62）。

⇒ 落成 `STREAMABLE_NODES`（**`:339`，放在图定义旁边，⛔ 别让端点自己抄一份**）：
```python
{"chat", "search_summarize", "translate_execute", "agent"}
```
⚠️ **`supervisor` 的字必须在过滤时丢掉** —— 而它会**真的出现在流里**（它也是个调 LLM 的节点），
实测见 `api/test_agent_stream_chains.py::test_chain_a_filters_out_supervisor_and_calc_execute`。

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/api_v1_agent.md` | **唯一入口** `POST /agent/advanced_chat`（`:434`）· 🆕 流式版 `POST /agent/advanced_chat/stream`（`:474`）· 那两道前置闸（B8 / B11） |
| `docs/specs/sse.md` | ⚠️ **本链的流式骨架** —— `sse_stream(graph_message_text(nodes=…))`；🔴 **链 A 是唯一必须 `subgraphs=True` 的一条** |
| `docs/specs/agent_graph_advanced.md` | ⚠️ **同一族的对照** —— 那边也有 ⚠️「名字骗人」与「同名不同义」两条 |
| `docs/specs/agent_checkpointer.md` · `docs/specs/agent_graph.md` | 另外两套图的 `agent/tools/approval` 节点（**同名碰撞**，见 ⚠️⑤） |
| `docs/specs/token_tracker.md` | ⚠️ **本模块不调用它** —— 见 §🟡 第一条（这正是要看的地方） |
| `docs/specs/safe_math.md` | `calculator` 的求值实现（`DEC-049`） |
| `fastapi-rag-agent-TODO待办/硬门A-Agent端流式勘察-20261003.md` §8.1 | ⭐ **「6 个只有 4 个该流」那张表最早落在这里** |
| `DEC-050` | 真流式的条件（声明 `config` + 转发给 `.stream()`）—— 本模块改造的依据 |
| `DEC-051` | 工具名两处来源 ⇒ 静默失效（本模块 `:38-56` 那次派生修正同源） |
