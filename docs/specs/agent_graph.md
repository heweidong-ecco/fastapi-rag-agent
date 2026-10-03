# `api/agent_graph.py`

| 项 | 内容 |
|---|---|
| **状态** | ⚰️ **遗留 / 未经裁决** —— **6 套 Agent 实现之一**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:22`）**改走 `llm_factory.make_llm("fast", "agent")`**。⚠️ **模型轴是 `fast`**（不是 chat）—— 这是改动前的实际取值，收口时**原样保留**<br>✅ 2026-10-03（**`②` Task 1 · `B4`**）：审批触发条件**从「任意 tool_calls」改成「工具白名单」**<br>✅ **2026-10-03（`DEC-049`）：`calculator` 的 `eval(expression)` 换成 `safe_math.calculate`** —— 本文件 **185 → 189 行**（多出的行是解释为什么不许改回去的注释）<br>🔵 **2026-10-03（`③` Task 4 · `B1`）：`agent_decide` 改成【流式可透传】的** —— 声明 `config: RunnableConfig` + 改用 `llm_with_tools.stream(…, config=config)` 逐块聚合。189 → **222 行**。📄 `DEC-050`<br>🔴 **2026-10-03（`DEC-051`）：两条既有 bug 结掉 + 搜索工具换掉** —— ①`tool_execute` 改成**查 `TOOLS_BY_NAME` 表**分派；②`SENSITIVE_TOOLS` 默认值改成真工具名 `web_search`，且 `validate_approval_config()` **加第二段硬拦**（名字不存在 ⇒ 拒绝启动）；③搜索工具 `DuckDuckGoSearchRun` → `search_tools.web_search`。222 → **258 行**（多出的行是"病根是名字有两个来源"的解释 + 新硬拦）。📄 `DEC-051`<br>⚠️ **行数口径**：本仓一律用 `scripts/spec_status.sh` 的数（= **真实行数**）。`wc -l` 对本文件**少算 1**（它末行没有换行符）⇒ 两边会差 1，⛔ **不是笔误**<br>⚠️ **`②` Task 2/3（`B5`/`B6`）⛔ 没动过本文件** —— 队列与续跑都落在 `api_v1_agent.py`（见下） |
| **对外提供** | 路由 `/agent/langgraph_chat` · `/agent/approve` |
| **谁在用** | `api_v1_agent.py:12`（`from agent_graph import agent_graph`） |

## ✅ 做了什么

- 基础 LangGraph Agent：`agent` 决策节点 → `tools` 执行循环
- 工具：**`web_search`（Bing 版，`search_tools`，`:48`）** · 计算器（**求值走 `safe_math`，`:26`**）· 日期（`:37`）
  · ⭐ **工具名只有 `tools` 一个来源** —— `TOOLS_BY_NAME = {t.name: t for t in tools}`（`:54`），`tool_execute`（`:151`）查它，⛔ 不许再抄名字
- **人工审批**：`interrupt_before=["approval"]`（`:183`）+ `/agent/approve` 端点
- 🔵 **流式（`③` Task 4 · `B1` · 2026-10-03）**：`agent_decide`（`:77`）声明 `config: RunnableConfig`，
  并用 `.stream(…, config=config)` 逐块聚合 ⇒ `/agent/langgraph_chat/stream` 的
  `astream(stream_mode="messages")` 才拿得到 **token 级**的块。📄 裁定 ⇒ `DEC-050`；
  ⚠️ **判据**（可打印）⇒ `api/test_agent_sse.py`（12 例，纯离线，进 CI）
- 🔵 **审批白名单**（B4）：`SENSITIVE_TOOLS`（`:68`，读 env，默认 **`web_search`**）· `needs_approval()`（`:185`）· `validate_approval_config()`（`:73`，启动自检**两段**：空名单 ⇒ `raise`；**名字不存在 ⇒ 也 `raise`**）

## 🟡 做到哪 / 缺什么

- ⚠️ **哪套 Agent 是"产品版本"——【未裁】**（属 **M5 的代际收敛**，见下）
- ✅ ~~**触发条件口径是错的**~~ ⇒ **2026-10-03 起【已修】**（B4）：`should_continue`（`:126`）现在是**三条路**（`approval` / `tools` / `END`），只有命中白名单才停
- ✅ ~~**`calculator` 是任意代码执行**~~ ⇒ **2026-10-03 起【已修】**（`DEC-049`）：改走 `api/safe_math.py`（AST 白名单求值 + 三道闸）。📄 见 **`docs/specs/safe_math.md`**
- ✅ ~~**零测试覆盖**~~ ⇒ **2026-10-03 起有 `api/test_approval_trigger.py`**（**8 例**，纯离线）+ **`api/test_tool_dispatch.py`**（**9 例**，含 2 条子进程起服自检）。⚠️ **覆盖范围只有审批触发条件与工具分派** —— **图的其余部分（节点行为 / 状态流转）仍无测试**
- ✅ ~~**`B5` 未做**~~ ⇒ **2026-10-03 起【已做】**（`②` Task 2）：待接管队列在 **`api/pending_approvals.py`**，出口是 **`GET /agent/pending`**（`api_v1_agent.py`）。📄 见 **`docs/specs/pending_approvals.md`**<br>⚠️ **但队列【不在这个模块里】** —— `agent_graph.py` 只负责"停下来"；"谁停下来了、从哪儿看"是 `api_v1_agent.py` 记账。⛔ 别在本模块找队列
- ✅ ~~**`B6` 未做**~~ ⇒ **2026-10-03 起【已做】**（`②` Task 3）：`/agent/approve` 加了 `edited_answer`（改写后提交），**续跑形状被 `api/test_approval_resume.py` 钉住**（`invoke(None, config)` = 从 checkpoint 继续）<br>⚠️ **同样不在本模块里** —— 改动落在 `api_v1_agent.py`。⛔ 本模块里**没有**续跑代码
- ⚠️ **硬门 D 三段齐了（`B4`/`B5`/`B6`），但【没有端到端验收过】** —— `B6` 只钉了接线与语义（假图），**"上下文真的连续"要真 LLM + 真 `MemorySaver` 跑一遍**才算（联网花钱）
- ✅ ~~**DuckDuckGo 本机不通**（`search_tools.py:48` 注明实测 `duckduckgo.com` 完全不通）⇒ 这条链上的搜索会失败~~
  ⇒ **2026-10-03 起【已修】**（`DEC-051`）：本文件改用 **`search_tools.web_search`（Bing 版）**。
  ⚠️ **但仍⛔ 不声明"搜索能用了"** —— 那要真联网，本机不可验证；本 DEC 只声明**"分派走对了"**（离线可验）。
- ✅ ~~🔴🔴 **`SENSITIVE_TOOLS` 的默认值【匹配不到任何真实工具】⇒ 审批其实【永不触发】**~~
  ⇒ **2026-10-03 起【已修】**（`DEC-051`）。改前实测（`③` Task 4 跑真服务时撞见）：
  真实工具名 = `['calculator', 'date_today', 'duckduckgo_search']`，而默认白名单写的是
  **`search_tool`**（**变量名**，⛔ 不是工具名）⇒ **交集为空** ⇒ **启动自检过得去，功能却从未生效过**。
  · ✅ **两处都补了**：默认值改成真工具名 `web_search`（`:68`），
    且 `validate_approval_config()`（`:73`）**加了第二段硬拦** —— 名字不在 `tools` 里 ⇒ **拒绝启动**。
  · ⚠️ **改前的失败形态正是硬门 D 说的那种**「**验收时才发现接管从来没发生过**」——
    `DEC-048 §四` 只拦了"空名单"，**没拦"名字不存在"** ⇒ 同一个失败**换了个形状绕过了它自己的闸**。
  · 📌 可打印的判据（修复后必须**非空**）：
    `{t.name for t in agent_graph.tools} & agent_graph.SENSITIVE_TOOLS` ⇒ `{'web_search'}`
  · 📌 守卫 ⇒ `api/test_tool_dispatch.py::test_shipped_default_whitelist_matches_a_real_tool`
    （**子进程**跑 —— 该常量是模块级读的，同进程改 env 无效）
- ✅ ~~🔴 **`tool_execute` 的分派名字也对不上** ⇒ **搜索工具永远执行不了**。（原 `:85`）~~
  ⇒ **2026-10-03 起【已修】**（`DEC-051`）。改前它判 `if tool_name == "search"`，
  而真名是 `duckduckgo_search` ⇒ 落到 `else`、返回字面量 `"未找到工具: …"`。
  · ⚠️ **后果是模型侧可见的**：真服务实测模型会**反复重试搜索** ⇒ 这正是 `③` Task 4 那个**多轮聚合缺陷**的触发器。
  · ✅ **现在查表**（`TOOLS_BY_NAME.get(name)`，`:172`）—— 名字**只从 `tools` 派生**，⛔ 不再有第二份。
  · 📌 守卫 ⇒ `api/test_tool_dispatch.py` **两道 AST**（分派里不许出现字符串字面量比较；
    全仓不许有第三个 `tool_execute` 抄名字）+ 一条**行为**（查不到时**如实**报 `未找到工具: xxx`，⛔ 不是 `KeyError`）
- ⚠️ **同型 bug 在本仓是【第二次】** —— `plan_execute.py:101-110` 记着上一回（prompt 写 `search`、
  注册表里叫 `web_search`）。⇒ 病根不是"写错了"，是**名字有两个来源**（`DEC-051 §一`）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「这是个产品功能」 | 🟡 **它是 6 套并存实现之一** —— 另 5 套：`agent_checkpointer` · `agent_graph_advanced` · `agent_graph_advanced_learning` · `/ws/agent` 的内联 Executor · `plan_execute`。<br>🔴 **哪套留下【未裁】**（`docs/CODE_INVENTORY.md` §7 明说「2 代与 3 代的先后顺序**从代码判不出**」） |
| 「有 `tool_calls` ⇒ 停在审批」 | 🔴 **2026-10-03（B4）起【不再】** —— 只有命中 `SENSITIVE_TOOLS` 才停（`should_continue`，`:195`）；**非敏感工具直接跑完**，无人值守。⚠️ **`api/test_agent_repairs.py:533` 与 `api_v1_agent.py:66` 的旧注释就在说这条**，已同步更正 |
| 「白名单 = 危险工具清单」 | ⚠️ **不是** —— 第一版只有 **`web_search`**（**外发数据**）。<br>✅ **2026-10-03 已结（`DEC-049`）**：`calculator` 原先那句 `eval(expression)`（**任意代码执行**）**已换成 `safe_math.calculate`**（AST 白名单求值）。⚠️ **但它仍然【不在】白名单里** —— 换成安全求值之后，"不出网"这条判据重新成立。<br>🔴 **改前实测（不是推演）**：喂 `__import__('os').system('touch /tmp/x')` ⇒ **命令真的跑了，且返回 `'0'`**（模型收到的是一条正常的"答案是 0"）。📄 见 `docs/specs/safe_math.md` |
| 「`.env` 里设了 `SENSITIVE_TOOLS`」 | ⚠️ **设不设都能跑** —— 不设走**默认值 `web_search`**（`:68`）。⇒ 想加/减**必须显式改 `.env`**。<br>🔴 **两种都会被启动自检拦住**（`validate_approval_config`，`:73`，**2026-10-03 `DEC-051` 起是两段**）：① **改成空** ② **写了不存在的工具名**。<br>⚠️ 第三档（**部分**名字不认识）**没有单独拦** —— 那时**整个启动被拒**，⛔ 不是"放过认识的那些"。 |
| 「审批是"全都接管"」 | 🔴 **不是** —— 硬门 D 要的是「**该被接管时被接管**」。改前"问个日期也停"那条路**验收过不去** |
| 「搜索工具还是那个 DuckDuckGo」 | ✅ **2026-10-03 起（`DEC-051`）本文件也换成了 `search_tools.web_search`** —— ⛔ 三份实现不齐的反例只剩 `api_v1_rag.py:746`（RAG 侧 `/ws/agent`，见 `DEC-051` 遗留·1） |
| 🔴 **「`SENSITIVE_TOOLS` 只是个开关，写个大概就行」** | ⛔ **它是【工具名】清单，⛔ 不是变量名** —— 写错一个字母的后果是**静默失效**（那个工具永不审批），**接口一切正常**。本仓**真的栽过**：默认值写成变量名 `search_tool`，**活了三天**（`DEC-051`）。<br>✅ 现在写错**会在启动时炸**，并**列出可用工具名**。 |
| 🔴 **「`agent_decide` 加个 `config` 参数只是顺手接一下」** | ⛔ **它是真流式的【唯一条件】** —— 不声明、或不转发进模型的**流式**调用，`astream(stream_mode="messages")` **只会吐 1 块**（整段，`on_llm_end` 发的）。<br>⚠️ 而**接口看上去完全正常**：照样 `text/event-stream`、照样有 `data:` 帧 —— **前端逐字显示是前端自己切的**。<br>📌 判据（可打印）：`api/test_agent_sse.py::test_graph_streams_one_chunk_per_token`（数**块数**，⛔ 不看 header） |
| 🔴 **「节点这么重，该改成 `async def` 吧」** | ⛔ **别改** —— 实测（探针⑧）会让**同步的** `graph.invoke()` 直接抛 `TypeError: No synchronous function provided to "agent"`，<br>而非流式路径（`/agent/langgraph_chat` · `api_v1.py` · `api_v1_rag.py`）**都在用它**。<br>✅ **同步节点 + 同步 `.stream(config)` 就能真流式**，⛔ 不需要 async。守卫 ⇒ `test_non_streaming_invoke_still_works` |
| ⚠️ **「聚合流式块，用 `content += ` 拼起来就行」** | ⛔ **会丢掉 `tool_calls`** —— 它是**碎片化**到达的（name 一块、args 几块）。<br>丢了 ⇒ `should_continue` 判不出 `"approval"` ⇒ **B4 审批静默失效**，而接口返回 `{"status":"answered"}` 一切正常。<br>✅ 必须用 LangChain 自带的 `AIMessageChunk.__add__`（`+`）。守卫 ⇒ `test_agent_decide_preserves_tool_calls` |

## 关联

`DEC-018`（Agent 目录处置）· **`DEC-048`（审批触发条件改工具白名单 —— 本模块 2026-10-03 那次改动的决策前提）** ·
**`DEC-051`（**工具名分派与白名单的标识符勘误** —— 本模块 2026-10-03 第二次改动：两条既有 bug + 换搜索工具）** ·
`ROADMAP` 待办 `T4`/`T5` · `docs/原理/架构.md` §1.3 ·
`后端补齐清单` **B4**（硬门 D 触发条件）· **`docs/specs/pending_approvals.md`**（`B5` 队列 —— ⚠️ **队列不本模块里**）·
`docs/specs/api_v1_agent.md` 的「实施计划 ②」
