# `api/agent_graph.py`

| 项 | 内容 |
|---|---|
| **状态** | ⚰️ **遗留 / 未经裁决** —— **6 套 Agent 实现之一**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:20`）**改走 `llm_factory.make_llm("fast", "agent")`**。⚠️ **模型轴是 `fast`**（不是 chat）—— 这是改动前的实际取值，收口时**原样保留**<br>✅ 2026-10-03（**`②` Task 1 · `B4`**）：审批触发条件**从「任意 tool_calls」改成「工具白名单」**<br>✅ **2026-10-03（`DEC-049`）：`calculator` 的 `eval(expression)` 换成 `safe_math.calculate`** —— 本文件 **185 → 189 行**（多出的行是解释为什么不许改回去的注释）<br>🔵 **2026-10-03（`③` Task 4 · `B1`）：`agent_decide` 改成【流式可透传】的** —— 声明 `config: RunnableConfig` + 改用 `llm_with_tools.stream(…, config=config)` 逐块聚合。本文件 **189 → 222 行**（多出的行全是"为什么必须这样写 / 为什么不许改成 `async`"的注释）。📄 `DEC-050`<br>⚠️ **行数口径**：本仓一律用 `scripts/spec_status.sh` 的数（= **真实行数**）。`wc -l` 对本文件**少算 1**（它末行没有换行符）⇒ 两边会差 1，⛔ **不是笔误**<br>⚠️ **`②` Task 2/3（`B5`/`B6`）⛔ 没动过本文件** —— 队列与续跑都落在 `api_v1_agent.py`（见下） |
| **对外提供** | 路由 `/agent/langgraph_chat` · `/agent/approve` |
| **谁在用** | `api_v1_agent.py:12`（`from agent_graph import agent_graph`） |

## ✅ 做了什么

- 基础 LangGraph Agent：`agent` 决策节点 → `tools` 执行循环
- 工具：**DuckDuckGo 搜索**（`DuckDuckGoSearchRun()`，`:42`）· 计算器（**求值走 `safe_math`，`:33`**）· 日期
- **人工审批**：`interrupt_before=["approval"]`（`:183`）+ `/agent/approve` 端点
- 🔵 **流式（`③` Task 4 · `B1` · 2026-10-03）**：`agent_decide`（`:77`）声明 `config: RunnableConfig`，
  并用 `.stream(…, config=config)` 逐块聚合 ⇒ `/agent/langgraph_chat/stream` 的
  `astream(stream_mode="messages")` 才拿得到 **token 级**的块。📄 裁定 ⇒ `DEC-050`；
  ⚠️ **判据**（可打印）⇒ `api/test_agent_sse.py`（12 例，纯离线，进 CI）
- 🔵 **审批白名单**（B4）：`SENSITIVE_TOOLS`（`:54`，读 env，默认 `search_tool`）· `needs_approval()`（`:116`）· `validate_approval_config()`（`:59`，启动自检，空名单直接 `raise`）

## 🟡 做到哪 / 缺什么

- ⚠️ **哪套 Agent 是"产品版本"——【未裁】**（属 **M5 的代际收敛**，见下）
- ✅ ~~**触发条件口径是错的**~~ ⇒ **2026-10-03 起【已修】**（B4）：`should_continue`（`:126`）现在是**三条路**（`approval` / `tools` / `END`），只有命中白名单才停
- ✅ ~~**`calculator` 是任意代码执行**~~ ⇒ **2026-10-03 起【已修】**（`DEC-049`）：改走 `api/safe_math.py`（AST 白名单求值 + 三道闸）。📄 见 **`docs/specs/safe_math.md`**
- ✅ ~~**零测试覆盖**~~ ⇒ **2026-10-03 起有 `api/test_approval_trigger.py`**（7 例，纯离线）。⚠️ **覆盖范围只有审批触发条件** —— **图的其余部分（节点行为 / 状态流转）仍无测试**
- ✅ ~~**`B5` 未做**~~ ⇒ **2026-10-03 起【已做】**（`②` Task 2）：待接管队列在 **`api/pending_approvals.py`**，出口是 **`GET /agent/pending`**（`api_v1_agent.py`）。📄 见 **`docs/specs/pending_approvals.md`**<br>⚠️ **但队列【不在这个模块里】** —— `agent_graph.py` 只负责"停下来"；"谁停下来了、从哪儿看"是 `api_v1_agent.py` 记账。⛔ 别在本模块找队列
- ✅ ~~**`B6` 未做**~~ ⇒ **2026-10-03 起【已做】**（`②` Task 3）：`/agent/approve` 加了 `edited_answer`（改写后提交），**续跑形状被 `api/test_approval_resume.py` 钉住**（`invoke(None, config)` = 从 checkpoint 继续）<br>⚠️ **同样不在本模块里** —— 改动落在 `api_v1_agent.py`。⛔ 本模块里**没有**续跑代码
- ⚠️ **硬门 D 三段齐了（`B4`/`B5`/`B6`），但【没有端到端验收过】** —— `B6` 只钉了接线与语义（假图），**"上下文真的连续"要真 LLM + 真 `MemorySaver` 跑一遍**才算（联网花钱）
- ⚠️ **DuckDuckGo 本机不通**（`search_tools.py:48` 注明实测 `duckduckgo.com` 完全不通）⇒ 这条链上的搜索会失败
- 🔴🔴 **`SENSITIVE_TOOLS` 的默认值【匹配不到任何真实工具】⇒ 审批其实【永不触发】**（2026-10-03 实测，`③` Task 4 跑真服务时撞见）。
  · 真实工具名 = `['calculator', 'date_today', 'duckduckgo_search']`（`t.name`），
    而默认白名单写的是 **`search_tool`**（那是**变量名**，⛔ 不是工具名）⇒ **交集为空**。
  · ⚠️ **这是 `.env` 没显式配时的默认路径**；`validate_approval_config()`（`:59`）**只查"非空"，
    不查"名单里的名字真的存在"** ⇒ **启动自检过得去，功能却从未生效过** ——
    正是硬门 D 说的那种「**验收时才发现接管从来没发生过**」。
  · ⛔ **不是 `③` 引入的**（`B4` 那天就在），但 **`③` 的真服务跑把它照出来了**。
  · 📌 可打印的判据：`{t.name for t in agent_graph.tools} & agent_graph.SENSITIVE_TOOLS == set()` ⇒ 空即中招
- 🔴 **`tool_execute`（`:85`）的分派名字也对不上** ⇒ **搜索工具永远执行不了**。
  它判 `if tool_name == "search"`，而真名是 **`duckduckgo_search`** ⇒ 落到 `else`，
  返回字面量 `"未找到工具: duckduckgo_search"`。
  · ⚠️ **后果是模型侧可见的**：真服务实测模型会**反复重试搜索**（收到的是"工具不存在"），
    一轮对话里连调好几次 ⇒ 这正是 `③` Task 4 那个**多轮聚合缺陷**的触发器。
  · ⛔ 同样**不是 `③` 引入的**。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「这是个产品功能」 | 🟡 **它是 6 套并存实现之一** —— 另 5 套：`agent_checkpointer` · `agent_graph_advanced` · `agent_graph_advanced_learning` · `/ws/agent` 的内联 Executor · `plan_execute`。<br>🔴 **哪套留下【未裁】**（`docs/CODE_INVENTORY.md` §7 明说「2 代与 3 代的先后顺序**从代码判不出**」） |
| 「有 `tool_calls` ⇒ 停在审批」 | 🔴 **2026-10-03（B4）起【不再】** —— 只有命中 `SENSITIVE_TOOLS` 才停（`should_continue`，`:122`）；**非敏感工具直接跑完**，无人值守。⚠️ **`api/test_agent_repairs.py:533` 与 `api_v1_agent.py:66` 的旧注释就在说这条**，已同步更正 |
| 「白名单 = 危险工具清单」 | ⚠️ **不是** —— 第一版只有 `search_tool`（**外发数据**）。<br>✅ **2026-10-03 已结（`DEC-049`）**：`calculator` 原先那句 `eval(expression)`（**任意代码执行**）**已换成 `safe_math.calculate`**（AST 白名单求值）。⚠️ **但它仍然【不在】白名单里** —— 换成安全求值之后，"不出网"这条判据重新成立。<br>🔴 **改前实测（不是推演）**：喂 `__import__('os').system('touch /tmp/x')` ⇒ **命令真的跑了，且返回 `'0'`**（模型收到的是一条正常的"答案是 0"）。📄 见 `docs/specs/safe_math.md` |
| 「`.env` 里设了 `SENSITIVE_TOOLS`」 | ⚠️ **设不设都能跑** —— 不设走**默认值 `search_tool`**（`:51`）。⇒ 想加/减**必须显式改 `.env`**；⚠️ **改成空**会让服务**启动就炸**（`validate_approval_config`，`:55`） |
| 「审批是"全都接管"」 | 🔴 **不是** —— 硬门 D 要的是「**该被接管时被接管**」。改前"问个日期也停"那条路**验收过不去** |
| 「搜索工具是真抓取」 | 🔴 **不是** —— 这里是**旧的 DuckDuckGo**；**新一代真抓取**（`search_tools.py` 的 `web_search`）**只接在 MCP 与 learning 版上** |
| 🔴 **「`agent_decide` 加个 `config` 参数只是顺手接一下」** | ⛔ **它是真流式的【唯一条件】** —— 不声明、或不转发进模型的**流式**调用，`astream(stream_mode="messages")` **只会吐 1 块**（整段，`on_llm_end` 发的）。<br>⚠️ 而**接口看上去完全正常**：照样 `text/event-stream`、照样有 `data:` 帧 —— **前端逐字显示是前端自己切的**。<br>📌 判据（可打印）：`api/test_agent_sse.py::test_graph_streams_one_chunk_per_token`（数**块数**，⛔ 不看 header） |
| 🔴 **「节点这么重，该改成 `async def` 吧」** | ⛔ **别改** —— 实测（探针⑧）会让**同步的** `graph.invoke()` 直接抛 `TypeError: No synchronous function provided to "agent"`，<br>而非流式路径（`/agent/langgraph_chat` · `api_v1.py` · `api_v1_rag.py`）**都在用它**。<br>✅ **同步节点 + 同步 `.stream(config)` 就能真流式**，⛔ 不需要 async。守卫 ⇒ `test_non_streaming_invoke_still_works` |
| ⚠️ **「聚合流式块，用 `content += ` 拼起来就行」** | ⛔ **会丢掉 `tool_calls`** —— 它是**碎片化**到达的（name 一块、args 几块）。<br>丢了 ⇒ `should_continue` 判不出 `"approval"` ⇒ **B4 审批静默失效**，而接口返回 `{"status":"answered"}` 一切正常。<br>✅ 必须用 LangChain 自带的 `AIMessageChunk.__add__`（`+`）。守卫 ⇒ `test_agent_decide_preserves_tool_calls` |

## 关联

`DEC-018`（Agent 目录处置）· **`DEC-048`（审批触发条件改工具白名单 —— 本模块 2026-10-03 那次改动的决策前提）** ·
`ROADMAP` 待办 `T4`/`T5` · `docs/原理/架构.md` §1.3 ·
`后端补齐清单` **B4**（硬门 D 触发条件）· **`docs/specs/pending_approvals.md`**（`B5` 队列 —— ⚠️ **队列不本模块里**）·
`docs/specs/api_v1_agent.md` 的「实施计划 ②」
