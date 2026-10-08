# `docs/specs/` —— 模块规格

> ## 这份目录回答什么
>
> ### **「有什么、没有什么、还缺什么模块？」**
>
> 本仓原先只有 `ROADMAP` 的**功能现状表**（按**功能**排：RAG检索 / 流式 / 认证 / 限额…），
> 但**没有任何地方能回答"这个模块做到哪了"** —— **要读代码才知道**。
> ⇒ **本目录补的就是这个。**
>
> ---
>
> ## 和别处的分工（**别读成重复**）
>
> | 想知道 | 去哪 | 视角 |
> |---|---|---|
> | **有哪些功能、什么状态** | `ROADMAP.md` 的功能现状表 | **按功能** |
> | **模块之间怎么连**（请求流 / 依赖） | `docs/原理/架构.md` | **架构视角** |
> | ⭐ **这个模块做到哪、看代码会误判什么** | **本目录**（一个模块一份） | **模块视角** |
> | 接口 / 环境变量 / 表结构 | `docs/契约/` | 契约视角 |

---

## 📋 模块对账表

<!-- MODULE-TABLE-BEGIN -->
<!-- 本表由 `bash scripts/spec_status.sh --write` 生成 —— ⛔ 别手改 -->

| 模块 | 行数 | spec | 自报状态 |
|---|---:|---|---|
| `api/agent_checkpointer.py` | 227 | ✅ [`specs/agent_checkpointer.md`](./agent_checkpointer.md) | 🟡 **地基在，但零测试 · 且有一处忽略配置**（117 → **121 行**，2026-10-03 `DEC-051`；🔵 2026-10-04 `B1` 后为 **171 行**；🔴 2026-10-04 `DEC-072` 后为 **192 行** —— `wc -l` 报 **191**，末行没有换行符，⛔ 差 1 不是笔误）<br>⚠️ **行数口径**：用 `scripts/spec_status.sh` 的数（= **真实行数**）。`wc -l` 对本文件**少算 1**（末行没有换行符）⇒ 两边会差 1，⛔ **不是笔误**<br>⚠️ **行号口径**：本 spec 的行号是 **2026-10-04（`DEC-072`）之后**的 `grep -n` 实测值。⚠️ 历史条目里带括注的大多是**当时**的值 —— 带「**现于**」的是**今天的值**；两者对不上**不是笔误**（`B1` + `DEC-072` 两次改动共下移了几十行）<br>✅ 2026-10-01：`llm`（现于 `:29`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:29`）**改走 `llm_factory.make_llm("fast", "agent")`** —— `model`/`api_key`/`base_url`/`max_tokens` 不再写在本地。⚠️ `bind_tools`（现于 `:51`）是**返回值必须是裸 `ChatOpenAI`** 的原因之一；⚠️ 另一个原因（记账要读 `model_name`）**已随 `DEC-072` 搬进 `token_tracker.record_from_response`**（本文件不再自己取模型名）<br>✅ **2026-10-03（`DEC-049`）：`calculator` 的 `eval(expression)` 换成 `safe_math.calculate`**（`:33`；新增 import 在 `:17`）。⚠️ **本模块的 `calculator` 是活的** —— 走 `/agent/memory_chat` 那条链<br>🔴 **2026-10-03（`DEC-051`）：两处修掉** —— ① `tool_execute`（现于 `:116`）改成**查 `TOOLS_BY_NAME` 表**分派（改前判 `if tool_name == "search"`、而真名是 `duckduckgo_search` ⇒ **搜索永远落 `else`**）；② 搜索工具换成 `search_tools.web_search`（`tools` 在 `:45`，表在 `:49`）。⚠️ **本模块的分派 bug 是"第二处现场"**（第一处在 `agent_graph.py`），且这条是**活路径**（`POST /agent/memory_chat`）。📄 `DEC-051`<br>🔵 **2026-10-04（`B1`）：`agent_decide` 改【流式可透传】** —— 声明 `config: RunnableConfig` + 换 `llm_with_tools.stream(…, config=config)` 逐块 `+` 聚合；新增模块级 `STREAMABLE_NODES = frozenset({"agent"})`（本文件的 `tools` / `approval` **不在**白名单里：它们不调 LLM，且 `tools` 返回的 `ToolMessage` 会被当成"新消息"发出来）。⚠️ **节点必须保持【同步】** —— `/agent/memory_chat` 走同步 `graph.invoke()`，改 `async def` 当场 `TypeError: No synchronous function provided to "agent"`（`DEC-050` 实测）。🔴 **顺带撞出一个既有 bug（⛔ 当时未修）**：那个 `hasattr(response, "usage")` 判据**恒为 False**（真消息只有 `usage_metadata`，没有 `.usage`）⇒ **本端点的记账从来没执行过**（配额形同虚设）。⛔ **修它 = 开始拦人，是行为变更** ⇒ 要单独裁。📄 勘察 §8.5<br>🔴 **2026-10-04（`DEC-072`）：那个恒假判据【已修】** —— `agent_decide`（现于 `:67`）改成 **`.stream()` 之前**查 `check_token_budget`（`:79`）、**之后**调 `record_from_response(…, "agent_decision", …)`（`:110`）；`AgentState`（`:54`）新增 `user_name` / `thread_id`（`:58` / `:59`，**由端点注入**）。171 → **192 行**。<br>⚠️ **这是【行为变更】**：`/agent/memory_chat` 的配额**从形同虚设变成真生效** —— 超预算的请求现在会被**拒**（返回 `BUDGET_EXCEEDED_MSG`），而改前一律放行。📄 `DEC-072` |
| `api/agent_graph.py` | 335 | ✅ [`specs/agent_graph.md`](./agent_graph.md) | ⚰️ **遗留 / 未经裁决** —— **6 套 Agent 实现之一**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:25`）**改走 `llm_factory.make_llm("fast", "agent")`**。⚠️ **模型轴是 `fast`**（不是 chat）—— 这是改动前的实际取值，收口时**原样保留**<br>✅ 2026-10-03（**`②` Task 1 · `B4`**）：审批触发条件**从「任意 tool_calls」改成「工具白名单」**<br>✅ **2026-10-03（`DEC-049`）：`calculator` 的 `eval(expression)` 换成 `safe_math.calculate`** —— 本文件 **185 → 189 行**（多出的行是解释为什么不许改回去的注释）<br>🔵 **2026-10-03（`③` Task 4 · `B1`）：`agent_decide` 改成【流式可透传】的** —— 声明 `config: RunnableConfig` + 改用 `llm_with_tools.stream(…, config=config)` 逐块聚合。189 → **222 行**。📄 `DEC-050`<br>🔴 **2026-10-03（`DEC-051`）：两条既有 bug 结掉 + 搜索工具换掉** —— ①`tool_execute` 改成**查 `TOOLS_BY_NAME` 表**分派；②`SENSITIVE_TOOLS` 默认值改成真工具名 `web_search`，且 `validate_approval_config()` **加第二段硬拦**（名字不存在 ⇒ 拒绝启动）；③搜索工具 `DuckDuckGoSearchRun` → `search_tools.web_search`。222 → **258 行**（多出的行是"病根是名字有两个来源"的解释 + 新硬拦）。📄 `DEC-051`<br>🔵 **2026-10-04（`B1` 剩余 4 条链）**：258 → **273 行** —— 新增模块级 `STREAMABLE_NODES` 及其说明注释（见下条）<br>⚠️ **行数口径**：本仓一律用 `scripts/spec_status.sh` 的数（= **真实行数**）。`wc -l` 对本文件**少算 1**（它末行没有换行符）⇒ 两边会差 1，⛔ **不是笔误**<br>⚠️ **行号口径**：非历史条目的行号是 **2026-10-04（`DEC-072`）之后**的 `grep -n` 实测值；**带日期条目里括注的行号是【当时】的值**（带「**现于**」的除外），两者对不上**不是笔误**<br>⚠️ **`②` Task 2/3（`B5`/`B6`）⛔ 没动过本文件** —— 队列与续跑都落在 `api_v1_agent.py`（见下）<br>🔵 **2026-10-04（`B1` 剩余 4 条链）：新增模块级 `STREAMABLE_NODES`**（现于 `:264`，现为 `frozenset({"agent"})`）—— **白名单住在图模块里**，端点只准按 `agent_graph.STREAMABLE_NODES` 取，⛔ 不许自己抄一份字面量（`DEC-051` 的教训：**一个名字两个来源必然漂移，而漂移是静默的**）。<br>⚠️ **为什么必须放模块级**：放进 `build_agent_graph()` 函数体就是**局部名** ⇒ 端点 `agent_graph.STREAMABLE_NODES` 直接 `AttributeError`（本批**真的踩过一次**才改过来）。📌 守卫 `api/test_agent_stream_chains.py::test_chain_a_whitelist_is_the_graph_module_s_own` |
| `api/agent_graph_advanced.py` | 472 | ✅ [`specs/agent_graph_advanced.md`](./agent_graph_advanced.md) | 🟡 **可用，且是生产链** —— 但 🔴 **有一处实锤缺陷**（见下；另一处 2026-10-05 已修）<br>✅ **2026-10-01 改完**：`B7` + `S12` 都已落在它的 `llm`（`:50`）上 —— 见「✅ 做了什么」末条<br>✅ **2026-10-02（`①b` Task 5）**：该 `llm` **改走 `llm_factory.make_llm("chat", "agent")`** —— `model`/`api_key`/`base_url`/`max_tokens` 不再写在本地。<br>⚠️ **`timeout` / `max_retries` 没丢**：它们走 `make_llm` 的 `**extra` **逐点透传**（这是本仓第一处用到 `**extra` 的地方）。<br>⚠️ **`llm.bind_tools(...)` 照旧能用**（那句在 `get_llm_with_mcp_tools()` 里，现于 `:295`；`llm_with_tools` 是 `:354` 拿到它的）—— 这正是「工厂返回值必须是裸 `ChatOpenAI`」那条约束的来由之一<br>🔵 **2026-10-04（`B1`）：两个节点改【真流式】** —— `chat_node`（`:315`）与 `agent_decide`（`:369`）都声明 `config: RunnableConfig` + 换 `async for chunk in llm.astream(…, config=config)` 逐块 `+` 聚合。⚠️ **本图的两个节点本来就是 `async`** ⇒ **走 `astream`**，⛔ 别照抄 `agent_graph.py` / `agent_checkpointer.py` 那两处（那两处是**同步**节点，改成同步会**阻塞事件循环**）。新增模块级 `STREAMABLE_NODES = frozenset({"agent", "chat"})`（`:304`）—— ⛔ **`tools` 不在里面**（它不调 LLM，且它返回的 `ToolMessage` 会被当成"新消息"发出去）。<br>⚠️ **`+` 聚合在本图是【必须】的**：`tool_calls` 碎片化到达，只拼 `content` 会丢掉它们 ⇒ `should_continue` 判不出 `"tools"` ⇒ **工具永远不会被执行**，而接口一切正常。📌 守卫 `api/test_agent_stream_chains.py::test_real_chain_c_nodes_stream_one_chunk_per_token`<br>🔴 **2026-10-05（`S13`）：预算拦截从【软】变【硬】** —— 被拦不再只是塞 `ToolMessage` 就继续走，而是**同时在 state 上写 `budget_intercept`**，两个端点据此回 **429 / error 帧**（改前是 HTTP 200，只有 LLM 知道被拦了）。⚠️ **同一批还堵掉一个更糟的现状**：被拦之后图**无条件回 `agent`** ⇒ 模型再调一次同一个工具、再被拦一次……改前实测直接 `GraphRecursionError: Recursion limit of 25 reached`（**在已判定"没钱了"之后又白烧十几轮 LLM**）⇒ 新增 `after_tools` 条件边，被拦即 `END`。📄 决策与**为什么不是在节点里 `raise`** ⇒ `docs/decisions/DEC-078` · 计划 ⇒ 下方「实施计划 · 批 2」<br>⚠️ **新 state 键 `budget_intercept`（`AgentState`）**：⛔ **没挂 `operator.add`** ⇒ last-write-wins + **落 checkpoint** ⇒ 由**入口节点 `agent_decide` 每轮开头清零**（它的**两个出口都带**）。🔒 守卫 `api/test_budget_hard_intercept.py::test_上一轮的拦截标志不会串到下一轮`<br>🔴 **2026-10-05（批 7 · `N11`）：本图【另两处】软返回一并收口** —— `chat_node`（兜底）与 `agent_decide`（入口）的 `check_token_budget` 软返回原先**只塞一句话当正常答案**（HTTP 200）⇒ 现在**同时写 `budget_intercept`**，端点回 **429 / error 帧**。⚠️ `agent_decide` 那处**语义翻转**（改前写 `**cleared` 显式清零 ⇒ 现在写本轮原因）；⚠️ **顺带堵掉"钱花在闸之前"**（`chat_node` 的记忆检索下移到门之后）。📄 `DEC-083` · 判据 `api/test_budget_soft_return.py`（21 例，**变异自证 27/27**） |
| `api/agent_graph_advanced_learning.py` | 593 | ✅ [`specs/agent_graph_advanced_learning.md`](./agent_graph_advanced_learning.md) | 🟡 **可用，且是生产链** —— ✅ **记账于 2026-10-04 补齐**（见下 `DEC-072`），⚠️ **两个分支本来就无字可流**（见下）<br>🔴 **2026-10-04（`DEC-072`）：6 个 LLM 调用点全部接上【预算拦 + 记账】** —— 改前本文件 `record_usage` / `check_token_budget` **0 命中** ⇒ 走 `/agent/advanced_chat` 的花销在 `token_usage_logs` 里**完全看不见**。450 → **540 行**。每个节点都是 **`.stream()`/`.invoke()` 之前**查 `check_token_budget(user_name, estimated_tokens=500)`、**之后**调 `record_from_response(…)`；`AgentState` 新增 `thread_id`（`user_name` 已有）—— **由端点注入**，子图与父图共用 `AgentState` ⇒ 身份自动流入子图。<br>⚠️ **`purpose` 五处取值**（`answer_generation` ×3 · `query_rewrite` ×1 · `agent_decision` ×2 —— 见「看代码会误判」表末行）<br>⚠️ **超预算的返回形状【按节点出口不同】** —— 见下方 ⚠️⑦：`supervisor` 那处**必须给 `intent`**，⛔ 否则 `route_by_intent` 读 `state["intent"]` 当场 `KeyError`。<br>📄 裁定 ⇒ `DEC-072`；📌 判据 ⇒ `api/test_billing_wiring.py`（AST 精确点名**本文件 6 条** + `-k behavior` 那条断言恰好 **2 笔**）<br>🔵 **2026-10-04（`B1` 剩余 4 条链）：4 个该流的节点改成【真流式】** —— `search_summarize`（`:143`）· `translate_execute`（`:237`）· `agent_decide`（`:279`）· `chat_node`（`:463`）都声明 `config: RunnableConfig` + 换 `.stream(…, config=config)` 逐块 `+` 聚合 ⇒ **本图 388 → 450 行**（多出的行是"为什么这 4 个流、那 2 个不流"的注释 + 白名单常量 + 每个节点的改法说明）。<br>⚠️ **本图 4 个节点【全是同步的】** ⇒ 走**同步** `.stream(config=config)`；⛔ **别照抄链 C**（`agent_graph_advanced.py` 那两个是 `async` ⇒ 用 `astream`），⛔ **也别把本图节点改成 `async def`** —— 同步的 `graph.invoke()` 会当场 `TypeError: No synchronous function provided to "agent"`（`DEC-050` 实测）。<br>新增模块级 `STREAMABLE_NODES`（`:399`）；**为什么必须放模块级**（放进 `build_advanced_agent()` 就是局部名 ⇒ 端点 `AttributeError`）写在 `:376-398` 的注释里。<br>🔴 **链 A 走 `astream` 时必须开 `subgraphs=True`** —— 本图 5 个子图，**不开它一个字都流不出来**（⚠️ 且 `meta["langgraph_node"]` 报的是**子图内层**名，见 ⚠️④）。⚠️ **`+` 聚合在本图同样【必须】**：`tool_calls` 碎片化到达，只拼 `content` ⇒ react 子图拿不到 `tool_calls` ⇒ **工具永远不执行**，而接口一切正常。<br>📌 守卫 `api/test_agent_stream_chains.py`（含 `test_real_chain_a_node_streams_one_chunk_per_token` · `test_chain_a_filters_out_supervisor_and_calc_execute`）<br>🔴 **2026-10-05（批 7 · `N11`）：6 处预算软返回全部收口**（`DEC-083`）—— 540 → **599 行**：每处**同时写 `budget_intercept`**；`supervisor` 的**软返回出口**由 `**cleared` 翻转成"写本轮原因"、**正常出口**（`:512`）写 `None`。<br>⚠️ **顺带堵掉"钱花在闸之前"**：`supervisor` 的记忆检索（`search_user_memory`）**下移到预算门之后**——改前被拒的那一轮照样花一次 embedding。📄 `DEC-083` §四·`🅕` |
| `api/answer_with_citations.py` | 84 | ✅ [`specs/answer_with_citations.md`](./answer_with_citations.md) | 🟡 **后端可用 · 但【默认不启用】—— 且零测试** |
| `api/api_v1.py` | 319 | ✅ [`specs/api_v1.md`](./api_v1.md) | ✅ **2026-10-04（`DEC-065`）鉴权与端点双收口** —— **9 条路由**里 **6 条带 `Depends(require_admin)`**，其余 3 条（`/` · `/auth/login` · `/auth/refresh`）是**有意公开**的 ⇒ **匿名可调的 = 0 条**（**唯一例外是本 spec 管不到的 `/api/v1/`，那是 `main.py` 的根路径**）。<br>🔴 **此前是**：「11 条路由里【只有 1 条】带鉴权依赖」—— 见下方 ⚠️①②③④ 四行，**四行都已随本次收口**（保留原文供查）<br>🔴 **2026-10-04（`DEC-065`）另删 2 条**：`/users/{user_id}`（**不查库**）· `/tool/benchmark`（**benchmark 的是 mock**）⇒ **11 → 9**<br>⚠️ **本 spec 曾推翻先前对 `B9` 的一个判断**（见 ⚠️②）<br>🔴 **2026-10-03（`①b` Task 6 · `DEC-046`）**：`/debug/quota` 的返回从「每日**次数**」换成「每日 **token**」—— **字段名没变、单位变了** |
| `api/api_v1_agent.py` | 2149 | ✅ [`specs/api_v1_agent.md`](./api_v1_agent.md) | 🟢 **可用；流式【5 条 · 对话链全齐】**（`③` Task 4 · `B1` · 2026-10-03 第一条 ⇒ **2026-10-04 补足剩余 4 条**）—— 5 条"会逐字生成答案"的链**全部**有 SSE 版本<br>⚠️ **其余 29 条（查询 / 管理 / 记账类）仍全非流式** —— 它们产出的**不是逐字生成的文本**（token 用量 / 工具健康 / 预算 / 轨迹 / 记忆增删），**流式对它们没有意义**。⛔ **这一条是【本批的判断】，没走业务裁定**（硬门 A 要的是"**该流的流**"）<br>✅ **改造收口**：本文件下方有 **实施计划 ②**（人工接管 · **已完成**）与 **③**（流式与取消 · **已完成** —— `B1`/`B2`/`B3` 全部落地，`B1` 的最后 4 条链于 **2026-10-04** 补齐）<br>✅ **2026-10-03（`②` Task 2 · `B5`）**：新增 **`GET /agent/pending`** ⇒ 路由 **28 → 29**<br>✅ **2026-10-03（`②` Task 3 · `B6`）**：`POST /agent/approve` 增加可选参数 **`edited_answer`** ⇒ **硬门 D 三段齐了**<br>🔵 **2026-10-03（`③` Task 4 · `B1`）**：新增 **`POST /agent/langgraph_chat/stream`**（SSE）⇒ 路由 **29 → 30**。📄 `DEC-050`<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：新加的这条流式路由**补上了 cancel 传播**（关图的流 + 记数）—— `DEC-050` §遗留·3 自己点的那个洞**已堵**。📄 `DEC-052`<br>🔴 **2026-10-03（`DEC-056` 丙段）· 三条口径变了**：<br>① **进图的 checkpoint 键**由裸 `thread_id` 改成 **`session_key(user_name, thread_id)`**（4 张图 · 7 处）；⚠️ **响应仍回显原值**<br>② **`/agent/approve` 加了归属校验**（**本人或 admin**）+ **按登记表里的 `graph` 字段路由**；⛔ 它**不再**直接吃 `agent_graph` 写死<br>③ **`/agent/memory_chat` 接上审批门**（`interrupt_before=["approval"]`）⇒ **`DEC-051` §遗留·2 关闭**<br>🔵 **2026-10-04（`B1` 剩余 4 条链）· 一次加 4 条流式路由** ⇒ 路由 **30 → 34**：`advanced_chat/stream`（`:889`）· `plan_execute/stream`（`:1128`）· `memory_chat/stream`（`:1311`）· `mcp_chat/stream`（`:1711`）。<br>· 同时**把原有的 `langgraph_chat/stream`（`:282`）一起改成走新共享层 `api/sse.py`** ⇒ 本文件里**不再有自己的 SSE 生成器**（逐帧等价，`test_agent_sse.py` + `test_cancel_propagation.py` 全绿且未改）。<br>· ⚠️ **每条都必须保留那两道前置闸**（`check_session_token_budget` `B8` + `circuit(global_key())` `B11`）—— 有两个 AST 守卫挖的是**端点函数体内部**（`api/test_session_budget_wiring.py:72` · `api/test_breaker_wiring.py:88`）⇒ **闸必须在函数体里，⛔ 不能挪进共享层**。<br>· 🔴 **链 D（`plan_execute/stream`）与 A/B/C **形态不同**：`plan_task` 是**同步函数**（跑在 `asyncio.to_thread` 里）⇒ 靠 **`_ThreadTokenBridge`**（`:1003`）把 token 从线程送回事件循环；且**它只流"规划段"**，之后是**一长段静默**（`execute_plan` 不流）—— ⛔ 别当成 bug。<br>🔵 **2026-10-04（`DEC-055`）· 5 条对话链全部接上 `chat_history` 留痕** —— 三条出口各写一个 `status`：`done` / `cancelled` / `error`。<br>· 🔴 **改前 5 条链【一条历史都不写】**（`grep -rn "append_chat_history" api/api_v1_agent.py` ⇒ **0**）—— 它们的"半路状态"由 **checkpointer** 持有，而 `chat_history` 是**另一套存储**（`DEC-055` §一 就查的这件事）。<br>· 🔴 **`done` 的答案取自【图的最终状态】（`aget_state` / `summary`），⛔ 不是 `on_complete` 收到的 `collected`**（`DEC-050` 真服务撞过的同一个坑：`calc_execute` 那种分支**一个字都不流**）。<br>· 🔴 **停在审批点（`status == "pending_approval"`）⇒ 本轮【不写】**（链 A 与链 B 各带这个 gate）—— 那时 `answer` 里是**模型已写的那半句（非空）**，不 gate 就会被写成 `status="done"`，正是本 DEC 要防的假信号。<br>📌 守卫 `api/test_agent_stream_chains.py`（**60 条** · 较评审收口时 **+13**，全是留痕那几条）· 骨架 ⇒ `docs/specs/sse.md`<br>🔴 **2026-10-04（`DEC-072`）· 6 个端点的初始 state 补上【身份】**：`user_name` / `thread_id` **必须进 state**（图里的记账节点靠它们才知道"这笔钱记给谁、记到哪个会话"）。<br>· 改动点：`langgraph_chat`（`:248`）· `langgraph_chat/stream`（`:414`）· `memory_chat`（`:1280`）· `memory_chat/stream`（`:1391`）—— 各加 `{"user_name": user_name, "thread_id": thread_id}`；<br>· 🔴 **`advanced_chat`（`:863`）/ `advanced_chat/stream`（`:973`）原先【只传了 `user_name`】，没有 `thread_id`** ⇒ 那两张图的账**只记得到人、记不到会话**。本批补齐。<br>· ⚠️ **传的是【原值】，⛔ 不是 `sess`（`session_key(...)` 那个）** —— `session_key` 是 **checkpoint 键**，与账目无关；写混了账会记到拼接后的键上。<br>· ⚠️ **缺身份不报错**：一律 `.get(…, "unknown")` 读 ⇒ 静默记成 `"unknown"`（⛔ 不是 500）。<br>📄 `DEC-072`；📌 判据 ⇒ `api/test_billing_wiring.py`（`ENDPOINTS` 6 条逐个查初始 state 有没有那两个键）<br>🔴 **2026-10-05（批 7 · `N11`）：9 条端点接上【图内拦截的出口形状】**（`DEC-083`）—— 4 条非流式 ⇒ **429**（判在 `summarize_agent_result()` 之前，⛔ 不许 `register`）· 4 条流式 ⇒ **error 帧 + `[DONE]` + `persist_turn(status="error")`**（⛔ 不发汇总帧）· `/agent/approve` ⇒ **补 `B8`+`B11` 两道门**（用调用方过门）+ **两个 `invoke` 都认标志**（命中先 `resolve` 再 429）。<br>⚠️ **改前这 8 条非-approve 端点会回 HTTP 200 + 一句"今日Token预算已用完"当答案** —— 调用方**看不出被拒了**。<br>⚠️ **`/agent/mcp_chat` 那条 429 的文案变了**（「本次**工具调用**未执行」→「**本轮**未继续执行」）—— 因为新增的软返回**根本没有工具调用**。📄 `DEC-083` §三<br>🔵 **2026-10-06（`DEC-088` · `F1` 接管页）· 一次加 2 条端点 ⇒ 路由 34 → 36**：<br>· 🆕 **`GET /agent/pending/context`（`:763`）** —— 待接管会话的**完整上下文**（`messages` 序列原样 + `owner`/`graph`/`rounds`/`next`）。可带**可选 `owner`**（裁定 6）收窄撞车的 `thread_id`；**多条候选 ⇒ 如实拒绝**，⛔ 不"挑第一条"。<br>· 🆕 **`GET /agent/approvals/history`（`:2021`）** —— 裁决历史（读 `api/approval_audit.py` 的 `approval_events` 表）。⚠️ **与 `/agent/pending` 同一条可见性口径**：本人默认、admin 全量。<br>· 🔴 **`GET /agent/pending`（`:702`）的可见性变了** —— 此前**跨用户全量**，现在**本人默认 · admin 全量**（`DEC-088` 缺口③）。⚠️ **收窄发生在【端点里】（两行过滤），`list_pending()` 一行没动** —— 见 `docs/specs/pending_approvals.md`。<br>· 🔴 **`POST /agent/approve`（`:439`）加了两样**：① 可选 **`owner`**（用来收窄撞车的 `thread_id`，**收窄 ≠ 授权**）② 每次**真裁决**写一条留痕（`record_decision`，fail-open）。⚠️ **留痕写在那道"队列登记陈了"的守卫【之后】** ⇒ 它是**第四条不记的出口**（见「看代码会误判」表）。<br>· 📄 设计 ⇒ `docs/decisions/DEC-088-接管页与硬门D的三个缺口.md` · 施工 ⇒ `fastapi-rag-agent-TODO待办/施工单-20261006-接管页.md` · ⚠️ **本批 ⛔ 不等于硬门 D 翻 ✅**（要照四硬门原文逐栏对）<br>🆕 **2026-10-06（`DEC-093` · `F2` Trace 页）· 加 1 条只读端点 ⇒ 路由 36 → 37**：<br>· 🆕 **`GET /agent/trace/{thread_id}/cost`** —— 成本轴（`token_usage_logs`）的逐笔明细 + 整条线程合计。⚠️ **它与 `/agent/trace/{thread_id}`（追踪轴 · 进程内存）是【两条轴】**，页面上并排画、**⛔ 不合并**（没有共同的步 id）。<br>· 🔴 **0 条回 200，⛔ 不是 404**（`thread_id` 是用户自己填的）；**取数⛔ 不复用 `get_thread_cost`**（它没有归属条件）。📄 `DEC-093` §三·A/§三·A' |
| `api/api_v1_rag.py` | 1148 | ✅ [`specs/api_v1_rag.md`](./api_v1_rag.md) | 🔵 **2026-10-06（`DEC-091` · `F4` 第一条）：`/rag/stream_search` 的帧集【再多一帧 `no_answer`】** —— 答案**以那句拒答语开头**时，在 `[DONE]` 之后、`sources` 之前多发一帧 `{"no_answer": true}`（`:840` 判 · `:841` 发）。<br>🔴 **判据在开头，⛔ 不是"含"**（`startswith`）；**prompt 与判据共用同一个模块级常量 `REFUSAL_SENTENCE`**（`:697`）—— 两处必须一致，而它们分家的表现是**静默的**（prompt 换了措辞 ⇒ 帧永远不发 ⇒ 页面上只是一句普通回答）。<br>⚠️ **⛔ 不提高拒答率**：prompt / 模型 / 检索**一行没动**，补的是**可观测性**。⛔ 也**不是**"加相似度阈值" —— 那条路已由三轮真栈 spike **结构性判死**（同文档邻居问题上量不出来，见 `DEC-091` §二/§三）。<br>⚠️ **对老前端天然兼容**：`sse.js` 认不出的帧落到 `'unknown'`，而页面**什么都不做**。<br>⚠️ **非流式那条链（`answer_with_citations.py`）一行没动** —— 它用的是**逐字同一句**，但**没有这个帧**，也**没有界面**；⇒ 🔴 **那句拒答语现在全仓有两份**，将来那边要加同样信号时**必须先收成一份**（`DEC-091` §八·2）。<br>🔴 **2026-10-05（`DEC-073`）：`/rag/search` 与 `/rag/rewrite_search` 补上 B8 + B11 两道闸**（`unified_search` `:534`/`:538` · `rewrite_search_api` `:480`/`:484`，各加 `thread_id: str = "default"`）—— **改前这两条链零闸**，而它们默认就真调 LLM。⚠️ **记账点不本文件**，在其下游（`rag_pipeline` / `answer_with_citations` / `query_rewriter`）。<br>✅ **2026-10-06（`DEC-084`）：`/rag/stream_search` 的流式答案【补上记账】** —— 端点里新增 `_StreamUsageTap`，用骨架本来就逐块调用的 `extract` 钩子累积所有块，收尾出口一次 `record_from_response(purpose="answer_generation")`。⚠️ **改前那句"流式 usage 拿不到"是错的**（见下方「看代码会误判」）—— 真根因是**没人读带 usage 的那一帧**（它 `content=''`，被 `llm_chunk_text` 判空丢掉）。⛔ **取消 / 异常仍不记**（那帧根本不到 · `DEC-053` §遗留·2）。<br>✅ **2026-10-04（`DEC-065`）：`tags=["模拟类测试"]` 整组【归零】** —— 另 **2 条**（`/rag/async_ask` · `/rag/parallel_ask`）**已删**（纯 mock · 零消费者）。本文件因此 **`@router.` 14 → 12**、**HTTP 12 → 10**。<br>⚠️ ⛔ **本文件现在没有任何"假端点"了** —— 剩下的 10 条 HTTP 条条都动真东西（库里/embedding/共享层）。<br>🔴 **2026-10-04（`DEC-064`）：`POST /rag/jwt_ask` 已【删除】** —— 三条理由与做法见 `docs/decisions/DEC-064-删除-rag-jwt-ask.md`。本文件因此 **`@router.` 15 → 14**、**HTTP 13 → 12**。<br>🟡 ~~部分可用 —— 有 2 条是"模拟类测试"（原 3 条；`/rag/ask` 2026-10-03 已删，`DEC-057`）~~ ⇒ **已归零**。<br>🔵 **2026-10-04（`B1` 剩余 4 条链 · 批 3）：`/rag/stream_search` 的 SSE 生成器【改成走共享层】** —— 内联的 `try/except/finally` 整段换成 `sse_response(sse_stream(...))`（`:731`）。<br>· 🔴 **行为必须【逐帧等价】，⛔ 不是"顺手统一"** ⇒ 三处**显式覆盖**骨架默认值：`ensure_ascii=True`（中文仍 `\uXXXX`）· `on_error`（**只有 error 帧、⛔ 不加 `[DONE]`**）· `chunk_delay=0.01`（限速照旧）。<br>· ⭐ **判据 = 既有两份用例"全绿且文件 diff 为空"**（`api/test_agent_sse.py` + `api/test_cancel_propagation.py`）—— ⛔ 没有新加断言 = 重构真的等价。<br>· ⚠️ **上游从同步 `.stream()` 改 `astream(messages)`（`:735`）不是本批的改动**（那是 `③` Task 5 · `B2`）；本批只是把它搬进 `lambda: …` 工厂。<br>📄 骨架见 `docs/specs/sse.md`<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：`/rag/stream_search` 的**取消传播做完了** —— 上游改 `astream`、`finally` 里 `aclose()` 关流、取消时记 `stream_cancelled_total`（`DEC-052`）。⚠️ **"上游真停"仍只有代码内证据**（本机无出账）<br>✅ **2026-10-03（`③` Task 6 · `B3`）**：中断后**那半截答案存进历史**（提问 + 半截 + `INTERRUPTED_SUFFIX` 标记，落 `finally` —— `DEC-053`）<br>✅ **2026-10-04（`DEC-055`）**：**三条出口都留痕，且各带一个 `status`** —— `done`（= 完整答案、⛔ 无标记）/ `cancelled` / `error`。🔴 改前 **`except Exception` 那条一个字都不留**（连提问一起丢）⇒ 现在也写了。留痕例程已收进 **`cache.persist_turn`**，本文件只剩**两个调用点**（`_complete` `:715` · `on_incomplete` `:745`）<br>🔴 ~~**未修**：**本文件的 LLM 调用一处都不记账**（`grep -c record_usage api/api_v1_rag.py` ⇒ **0**）⇒ 见下方「做到哪」与 `DEC-053` §遗留·2~~ ⇒ **2026-10-05（`DEC-073`）部分修复**：`/rag/search` 与 `/rag/rewrite_search` 两条链**记账点在下游模块**、闸在本文件；⛔ **`/rag/stream_search` 与两条 Agent 路径仍未修** ⇒ 见下方「做到哪」<br>✅ 2026-10-01：两处 `ChatOpenAI`（**当时** `:578` 流式答案 · `:751` WS agent）接上 `MAX_TOKENS_ANSWER`（`B7`）—— ⚠️ **两处都已不存在**：2026-10-02 起改走 `llm_factory.make_llm("chat","answer")`（见下一条），`ChatOpenAI` 早已不是本文件的调用形状<br>✅ 2026-10-02（`①b` Task 5）：那两处**改走 `llm_factory.make_llm("chat", "answer")`** ⇒ **本文件已不再 import `ChatOpenAI` / `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_CHAT`**。<br>⚠️ **`get_llm_stream()` 的惰性没变**（`make_llm` 自己把 langchain 的 import 关在函数内）· ⚠️ `temperature=0.3` + `streaming=True` 是**本处特有的逐点调参**，仍写在调用点上 |
| `api/approval_audit.py` | 110 | ✅ [`specs/approval_audit.md`](./approval_audit.md) | （未写） |
| `api/auth.py` | 216 | ✅ [`specs/auth.md`](./auth.md) | ✅ **可用（生产）** —— 两条并行的认证：**API Key**（查库）与**登录口令**（比环境变量） |
| `api/bm25_index.py` | 142 | ✅ [`specs/bm25_index.md`](./bm25_index.md) | 🟡 **可用** —— 且 **2026-10-03 起它是「多用户隔离」的两个承重层之一**（`DEC-056` 决策 5：过滤写在共享层） |
| `api/breaker.py` | 78 | ✅ [`specs/breaker.md`](./breaker.md) | 🟡 **部分** —— `global:` 这一条 key **已生效**（2026-10-02 · `①b` Task 4）；`model:` 那类**还没做**（留给 `L2`） |
| `api/browser_tools.py` | 84 | 🔴 **缺** | ❓ 未知 |
| `api/cache.py` | 138 | ✅ [`specs/cache.md`](./cache.md) | ✅ **可用（生产）** —— 🔴 **两类完全不同的东西住在同一份文件里**（embedding 缓存 + 对话历史） |
| `api/chunker.py` | 66 | ✅ [`specs/chunker.md`](./chunker.md) | 🟡 **可用** —— 但**五档配置里只有两档真被用到**，且**零测试** |
| `api/code_executor.py` | 150 | ✅ [`specs/code_executor.md`](./code_executor.md) | ✅ **可用 · 已进容器（2026-10-08 · 批②）** —— 改前是「宿主同权限的子进程 + 白名单」 |
| `api/code_executor_impl.py` | 292 | 🔴 **缺** | ❓ 未知 |
| `api/config.py` | 90 | ✅ [`specs/config.md`](./config.md) | ✅ **可用** —— **全仓环境变量的唯一入口**（规范要求⛔ 不许别处 `os.getenv`）。⚠️ 但它有**两处 import 期副作用** |
| `api/cost_dashboard.py` | 294 | 🔴 **缺** | ❓ 未知 |
| `api/db.py` | 309 | ✅ [`specs/db.md`](./db.md) | 🟡 **可用** —— 连接池 + 建表 + 向量检索；**2026-10-03 起它同时是「多用户隔离」的两个承重层之一**（`DEC-056` 决策 5） |
| `api/db_metadata.py` | 87 | ✅ [`specs/db_metadata.md`](./db_metadata.md) | ⚰️ **不是运行时模块** —— 它是 **Alembic autogenerate 用的声明式镜像**，**⛔ 不是表结构的真值** |
| `api/deps.py` | 201 | ✅ [`specs/deps.md`](./deps.md) | 🟡 部分可用 —— **HTTP 侧完整**；**WebSocket 侧 2026-10-05 才补上**（此前 WS 整条裸奔） |
| `api/document_parser.py` | 242 | 🔴 **缺** | ❓ 未知 |
| `api/document_preprocessor.py` | 221 | 🔴 **缺** | ❓ 未知 |
| `api/embedding_client.py` | 78 | ✅ [`specs/embedding_client.md`](./embedding_client.md) | ✅ **客户端已惰性构造**（2026-10-05 · 批 6 · `T1` · `DEC-082`） |
| `api/exceptions.py` | 82 | 🔴 **缺** | ❓ 未知 |
| `api/executor_server.py` | 120 | ✅ [`specs/executor_server.md`](./executor_server.md) | ✅ **上线（2026-10-08 · 批②）** —— 服务本体 + compose 硬化 + 应用接线 + 并发上限，**全部已实测** |
| `api/hybrid_search.py` | 149 | ✅ [`specs/hybrid_search.md`](./hybrid_search.md) | 🟡 **可用，但它在全仓是【第二份 RRF 实现】** |
| `api/jwt_handler.py` | 74 | 🔴 **缺** | ❓ 未知 |
| `api/llm_factory.py` | 156 | ✅ [`specs/llm_factory.md`](./llm_factory.md) | 🟢 **新建（2026-10-02 · `①b` Task 5）** —— LLM 客户端的**唯一构造落点**<br>✅ 15 个调用点**已全部改走它**（`api/test_max_tokens_wiring.py` 钉着）<br>⬜ **自动兜底没做**（评估后**故意推迟**，见下）—— ⛔ 别以为它能"兜底" |
| `api/logger_config.py` | 53 | 🔴 **缺** | ❓ 未知 |
| `api/main.py` | 787 | ✅ [`specs/main.md`](./main.md) | 🟡 **可用** —— 应用装配 + **3 条中间件** + 全局异常处理 + 看板挂载 + **3 条页面路由**<br>✅ 2026-09-30 起**限流分桶会验签了**（修 `B9-b`）· ✅ **4 处错误文案已修 + 加了 `retry_after`**（修 `B12`）<br>🔴 **2026-10-03（`①b` Task 6 · `DEC-046`）：`QuotaMiddleware` 的额度口径从「每日请求【次数】」换成「按用户按天 **token**」**（= `R1.3`）。<br>🔴 **2026-10-05（批 3 · `N9`）：两条中间件在【依赖不可用】时都改为 fail-open** —— 限流侧身份 `None` ⇒ 跳过用户级限流；额度侧身份 `None` ⇒ 跳过额度检查（`DEC-079`）。<br>🆕 **2026-10-06（`DEC-088` · `F1`）：新增第二条页面路由 `GET /approvals`** —— 与 `/chat` **逐条同构**（302 · `include_in_schema=False` · 显式进无鉴权基线 · 各 3 条页面用例）。<br>🔵 **2026-10-06（`DEC-090` · `F4` 第三条）：异常处理器多写一个【可选】`scope`**（与 `retry_after` 同套路，见「做到哪」）。<br>🆕 **2026-10-06（`DEC-093` · `F2`）：新增第三条页面路由 `GET /trace`** → 302 `/static/web/trace.html` —— 同样与 `/chat` 同构，但**它的页面用例是 6 条不是 3 条**（多出 3 条页面坏法的守卫，见「做到哪」）。<br>🔧 **2026-10-06（`DEC-094`）：页面路由【代码本身没动】** —— 本份记的是 `approvals.html` 的 4 条 URL 前缀与 `ci.yml` 的 `node --test`，**两条都不在这个模块里**；⚠️ 唯一相关的是「页面守卫从"盯一个页面"改成"盯全站"」⇒ 见「看代码会误判」。 |
| `api/mcp_server.py` | 135 | 🔴 **缺** | ❓ 未知 |
| `api/mcp_tool_factory.py` | 106 | 🔴 **缺** | ❓ 未知 |
| `api/memory_store.py` | 72 | 🔴 **缺** | ❓ 未知 |
| `api/metrics.py` | 54 | ✅ [`specs/metrics.md`](./metrics.md) | ✅ **可用** —— 4 个指标，全部走 `prometheus_client` 默认 REGISTRY<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：新增 **`stream_cancelled_total`** —— 它是判据③**唯一可执行的观测对象**（`DEC-052`） |
| `api/pending_approvals.py` | 143 | ✅ [`specs/pending_approvals.md`](./pending_approvals.md) | 🆕 **新建（2026-10-03 · `②` Task 2 · `B5`）** —— 待接管队列（硬门 D 的"数据"那一半）<br>🔴 **2026-10-03 丙段改键**：登记键由**裸 `thread_id`** 改成 **`session_key(user_name, thread_id)`**，并新增 `raw_thread_id` / `graph` 两个字段<br>🔴 **2026-10-05 加轮次上限**（`DEC-062 §六·2`）：新增 `rounds` 字段 + `approval_round_cap()`，让"放行后又停"**有界** |
| `api/permission.py` | 57 | ✅ [`specs/permission.md`](./permission.md) | 🟡 **可用 —— 但它是【硬编码】的**：`admin` 特判 + 探针身份特判，其余一律 `FREE`。⛔ **接 DB 这件事仍挂起** |
| `api/plan_execute.py` | 695 | ✅ [`specs/plan_execute.md`](./plan_execute.md) | 🟡 **可用** —— 规划 + 逐步**真调用工具**；有超时、有总预算、有重规划、有降级<br>✅ **2026-10-05（批 1 · `S9`/`S10`）**：`⚠️①`（重规划漏传 `user_name`）与 `⚠️②`（成败判定读中文文案）**均已修** ⇒ **`⚠️` 表 6 行里还剩 ③④⑤⑥ 共 4 行**（⚠️ 都是**说明**不是缺陷）<br>⛔ **原「1 处真缺陷 + 5 处会误判」的账已销**（`S11` 见 `🟡 做到哪`）<br>🔵 **2026-10-04（`B1` 剩余 4 条链）：`_invoke_llm` / `plan_task` 各加一个 `on_token` 形参** —— 给 `/agent/plan_execute/stream` 用。<br>· ⚠️ **默认 `None` ⇒ 行为一字符不变**（`on_token is None` 时仍走 `llm.invoke`，`:155`）。<br>· ⚠️ **⛔ 它只让「规划段」能流** —— `execute_plan` / `generate_dynamic_input` / 质量检查**都还是非流式**（业务方 2026-10-04 裁「只流规划段」）⇒ **规划段之后是一长段静默**。<br>· 🔴 **流出的是【正在生成的 JSON 片段】**（提示词要求严格 JSON）⇒ ⛔ 前端别把流到的文本直接渲染成计划，只当"规划中"指示器。<br>· ⭐ **一条实现约束**：聚合循环**必须遍历【所有】块**（含 `content` 为空的）—— provider 把 `usage_metadata` 挂在**最后一块**上，跳过它**账就没了**（实测，探针 `探针-流式与记账.py`）。<br>· 📄 端点在 `docs/specs/api_v1_agent.md` Task 7 · 桥在 `_ThreadTokenBridge`<br>✅ 2026-10-01：三个 `_llm` 接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：三个 `_llm` **改走 `llm_factory.make_llm("chat", "agent")`**（现于 `:92` / `:279` / `:486`）—— `model`/`api_key`/`base_url`/`max_tokens` 不再写在本地。<br>⚠️ **超时/重试没丢**：`timeout` / `max_retries` 走 `make_llm` 的 `**extra` **逐点透传**，**值一字符未变**（30/20/15 + `LLM_MAX_RETRIES`）。<br>⚠️ `executor_llm` 的 `temperature=0.1` 是**本文件特有的**逐点调参，仍写在调用点上<br>⚠️ **行号口径**：本 spec 的行号为 **2026-10-04 之后**的实测值（`grep -n` 复核）；批 4 之后**执行段整体下移 ~28 行**，⛔ 别拿旧行号去找 |
| `api/query_rewriter.py` | 193 | ✅ [`specs/query_rewriter.md`](./query_rewriter.md) | 🟢 **可用；2026-10-05 起它真记账了**（此前 `record_usage` **import 在、调用 0 次**） |
| `api/rag_pipeline.py` | 263 | ✅ [`specs/rag_pipeline.md`](./rag_pipeline.md) | ✅ **可用（生产）** —— `/rag/search` 的**唯一**检索管线。⚠️ 但里面有**一段死代码**和**一条没有过滤的档位** |
| `api/rate_limiter.py` | 211 | ✅ [`specs/rate_limiter.md`](./rate_limiter.md) | 🟡 **可用** —— 基于 Redis 的令牌桶，**全局 + 用户两层**<br>🔴 它曾有 **3 个"看代码看不出来"的性质** ⇒ **2026-10-05（批 3 · `S7`/`S8`）起 ②③ 已修、① 早于 2026-09-30 已修**（`B9-b`）<br>⚠️ **但 ⚠️ 节还在** —— ①④⑤ 仍然是"看代码会误判"的（其中 ④ 是**已知未修**），⛔ 别因为"②③修了"就当整节过时了 |
| `api/reranker.py` | 59 | ✅ [`specs/reranker.md`](./reranker.md) | 🟡 **仅开发机可用** |
| `api/safe_math.py` | 235 | ✅ [`specs/safe_math.md`](./safe_math.md) | 🟢 **新建（2026-10-03 · `DEC-049`）** —— `calculator` 工具的**求值实现**，替代 `eval(expression)` |
| `api/schemas.py` | 104 | 🔴 **缺** | ❓ 未知 |
| `api/search_tools.py` | 153 | ✅ [`specs/search_tools.md`](./search_tools.md) | ✅ **可用** —— 但它是**抓网页**的做法：**必应一改版就坏**，⚠️ **坏得响**（如实报失败，⛔ 不退回"让模型编"） |
| `api/session_key.py` | 60 | ✅ [`specs/session_key.md`](./session_key.md) | 🆕 **新建（2026-10-03 · `DEC-056` 丙段）** —— 会话键：**把身份拼进 checkpoint / 会话 id** |
| `api/simple_tools.py` | 109 | 🔴 **缺** | ❓ 未知 |
| `api/simple_tools_impl.py` | 134 | 🔴 **缺** | ❓ 未知 |
| `api/sse.py` | 282 | ✅ [`specs/sse.md`](./sse.md) | 🟢 **新建并已接上全部 6 条流式端点（2026-10-04 · `③` Task 4 · `B1` 剩余 4 条链）** —— 本仓**所有流式端点的骨架**<br>⚠️ **它收的不是"重复代码"，是 5 条实测出来的顺序约束**（`DEC-054` / `DEC-052` / `DEC-050`）<br>✅ 批 2 建层 + 单测 · 批 3 两条旧端点改用它（**逐帧等价**）· 批 5 的 4 条新链**一开始就建在它上面** |
| `api/token_config.py` | 116 | ✅ [`specs/token_config.md`](./token_config.md) | 🟢 **新建（2026-10-01 · B7）** —— 额度类常量的**唯一落点**<br>✅ **`MAX_TOKENS_*` 已接线**（2026-10-01 · `①b` Task 1，15 处构造点；**2026-10-02 · Task 5 起收进 `api/llm_factory.py`**）<br>✅ **`SESSION_TOKEN_LIMIT` 已有判定函数 + 7 个调用点**（`①b` Task 2 · `B8`）<br>✅ **`GLOBAL_DAILY_TOKEN_LIMIT` 已接线**（2026-10-02 · `①b` Task 4 · `B11`，经 `api/breaker.py` **8 处**）<br>⚠️ **2026-10-01 当天它曾是"有函数、无调用点"—— 那句已作废** |
| `api/token_tracker.py` | 1229 | ✅ [`specs/token_tracker.md`](./token_tracker.md) | 🟡 **可用** —— ⚠️ **2026-10-03 起它不再是"三套口径"之一**（次数那套已删，`DEC-046`）<br>🟢 **①a 已落地（2026-10-01）**：额度常量已收口到 `api/token_config.py`（本文件**只剩同名别名**）· 本文件下方 **实施计划 ①a** 已执行完<br>🔵 **①b（2026-10-02）**：Task 0 ✅ / Task 1 ✅（B7 接线）/ **Task 2 ✅（B8 会话级 · 已接 7 条链）** / **Task 3 ✅（B10 全局日级 · 判定函数）** / **Task 4 ✅（B11 熔断 · 已接 8 处，`B10` 由此生效）** / **Task 5 🟡 部分（`L2`）**（改写后只做构造收口，⛔ 自动兜底【推迟】—— 见该 Task 的修订块） / **Task 6 ✅（`决策一` 落地 · `DEC-046` —— 撤次数配额、原位换 token 口径 = `R1.3`）** / **Task 7 ✅（`B13` 实跑核成本可见 · `DEC-047` —— `①b` 收尾）**<br>⚠️ **`B10` 曾一度"有函数没接线"（2026-10-01 当天）—— 那句话已作废**，2026-10-02 Task 4 接上了<br>🔴 **2026-10-04（`DEC-072`）：新增 `record_from_response()` —— 【取用量的唯一实现】** —— 962 → **1027 行**。改前"从响应取 usage"这件小事**在每条链里各写一遍**，于是三条链里有的**写错了属性名**（`.usage` 恒假）⇒ **静默不记账**。现在**三张图 9 个调用点**统一调它，⛔ 不许再各写各的。<br>⚠️ **它只做「取+记」，⛔ 不做「拦」** —— 拦是 `check_token_budget` 的事，由**调用方在 `.stream()` 之前**自己调 |
| `api/tool_cache.py` | 207 | ✅ [`specs/tool_cache.md`](./tool_cache.md) | ✅ **已接进产品路径（2026-10-08 · 批①）** —— 🔴 **此前它是"没接上的模块"**（整块死代码，见下） |
| `api/tool_health.py` | 113 | ✅ [`specs/tool_health.md`](./tool_health.md) | 🟡 **可用 —— 但它只【记录】健康状态，⛔ 不做降级** |
| `api/tool_visualizer.py` | 174 | ✅ [`specs/tool_visualizer.md`](./tool_visualizer.md) | 🟡 **部分可用** —— 记录与查询都在，但① 存储是**进程内存**（重启即空）② **只有一个端点**（`/agent/mcp_chat`）往里写 |
| `api/websocket_callback.py` | 90 | 🔴 **缺** | ❓ 未知 |
<!-- MODULE-TABLE-END -->

> ⛔ **这张表【不要手改】** —— 它是 `scripts/spec_status.sh --write` 生成的。
> 理由同 `list_endpoints.sh`：**手写的清单必然过期**。
>
> 📌 **`spec` 列写「🔴 缺」的，就是"还没人核过这个模块做到哪"** —— **那本身就是信息。**

---

## 怎么写一份 spec

**一个模块一份**，文件名 = 模块名（`api/reranker.py` ⇒ `docs/specs/reranker.md`）。

```markdown
# `api/<模块>.py`

| 项 | 内容 |
|---|---|
| **状态** | ✅ 完整 / 🟡 部分可用 / ⬜ 未做 / ⚰️ 遗留（看代码会以为是产品功能） |
| **对外提供** | 函数 / 类 / 端点 |
| **谁在用** | |

## ✅ 做了什么
## 🟡 做到哪 / 缺什么
## ⚠️ 看代码会误判的地方        ← ⭐ **这一节是整份 spec 的价值所在**
## 关联
```

> ### ⭐ 为什么第三节最重要
>
> **前两节读代码也能推出来** —— 只有第三节**读代码推不出来**。
>
> 真实例子：
> ```
> api/reranker.py     文件在、代码完整 ⇒ 看着像"做完了"
>                     实际：镜像里没装 torch ⇒ 【容器里跑不了】
>
> api/agent_graph.py  4 套 Agent 实现之一 ⇒ 看着像"产品功能"
>                     实际：哪套是产品版本【未裁】(M5)
>
> api/api_v1_rag.py   15 条端点 ⇒ 看着像个正经模块
>                     实际：里面 3 条是"模拟类测试"（返回假数据）
> ```

---

## 状态图例

| 图例 | 意思 |
|---|---|
| ✅ **完整** | 功能完整、可用、**且验证过** |
| 🟡 **部分可用** | 能跑但有明确限制（写在 §🟡） |
| ⬜ **未做** | 代码骨架在，功能没实现 |
| ⚰️ **遗留** | 已被取代 / 不打算维护，**但还在线上**（看代码会误判） |
| ⚰️ **已删除** | **模块已经没了** ⇒ 本目录下**不该再有**它 —— **spec 移到 [`归档/`](./归档/README.md)** |
| ❓ **未知** | **还没人核过** —— 不是"没问题" |

---

## 🔧 怎么维护（**四条**）

| # | 什么时候 | 做什么 |
|---|---|---|
| 1 | **做完一个模块的功能** | ⭐ **更新它的 spec**（`CLAUDE.md` 的规矩） |
| 2 | **新增一个模块** | ⭐ **必须同时建 spec** —— **`pre-commit-gates.py` 会【硬拦】** |
| 3 | **删掉一个模块** | ⭐ **spec 移到 [`归档/`](./归档/README.md)** + 顶部加「⚰️ 已归档」头（⛔ **不是删掉它** —— 「⚠️ 看代码会误判的地方」是**花钱测出来的**） |
| 4 | 想起来的时候 | 跑 `bash scripts/spec_status.sh` 看**还缺哪些 / 有没有残留** |

```bash
bash scripts/spec_status.sh            # 对账：谁有 spec、谁没有、谁的模块没了
bash scripts/spec_status.sh --write    # 顺带重写上面那张模块表
bash scripts/spec_status.sh --missing  # 只列缺的
```

📌 **也可以打 `/specs`**（斜杠命令，见 `.claude/commands/`）。
📌 **第 3 条的判据（可打印）**：`bash scripts/spec_status.sh` 的 **`🗑 spec 有、代码没了`** 一行 —— **应为 0**。
（脚本只扫 `docs/specs/*.md`、**不递归子目录** ⇒ 移进 `归档/` 就等于解掉这条告警。）
**2026-10-03 首次用到**：`quota_limiter.md`（`DEC-046` 删了那个模块）。

---

## ⚠️ 一条已知的局限（**别指望它 100% 准时**）

**spec 是人/agent 写的 ⇒ 它会过期。** hook 只能**拦住"新增模块没 spec"**（能机械判），
**"改了已有模块要不要更新 spec"是判断，机械判不了** ⇒ 只能**提醒**。

⇒ **所以第 3 条（跑对账）才是最终兜底。**
📌 本仓对这类事有明文教训：「**门挂在别处，就等于没有门**」——
**8 个 PR 一次都没跑过 `/留痕-checks`**。**⇒ 对账能查出来，就不算失控。**

---

## ⚙️ 本目录的自动机制（**2026-09-29 建**）

| 机制 | 在哪 | 拦不拦 |
|---|---|---|
| **提交前第 ④ 道门** | `.claude/hooks/pre-commit-gates.py` | ✅ **硬拦**：**新增了 `api/X.py` 但 `docs/specs/` 下与模块同名的那个文件 不存在** |
| **写完 `api/*.py` 后提醒** | `.claude/hooks/spec-remind.py` | ⛔ 不拦（写代码过程中太频繁） |
| **`/specs` 命令** | `.claude/commands/specs.md` | 手动跑对账 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/文档地图.md` | 全项目文档索引 |
| `docs/原理/架构.md` | 架构视角（模块怎么连） |
| `ROADMAP.md` | 功能视角（有哪些功能） |
| `scripts/spec_status.sh` | 对账脚本 |
