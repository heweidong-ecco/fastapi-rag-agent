# `api/agent_graph.py`

| 项 | 内容 |
|---|---|
| **状态** | ⚰️ **遗留 / 未经裁决** —— **6 套 Agent 实现之一**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:20`）**改走 `llm_factory.make_llm("fast", "agent")`**。⚠️ **模型轴是 `fast`**（不是 chat）—— 这是改动前的实际取值，收口时**原样保留**<br>✅ 2026-10-03（**`②` Task 1 · `B4`**）：审批触发条件**从「任意 tool_calls」改成「工具白名单」** |
| **对外提供** | 路由 `/agent/langgraph_chat` · `/agent/approve` |
| **谁在用** | `api_v1_agent.py:12`（`from agent_graph import agent_graph`） |

## ✅ 做了什么

- 基础 LangGraph Agent：`agent` 决策节点 → `tools` 执行循环
- 工具：**DuckDuckGo 搜索**（`DuckDuckGoSearchRun()`，`:38`）· 计算器 · 日期
- **人工审批**：`interrupt_before=["approval"]`（`:179`）+ `/agent/approve` 端点
- 🔵 **审批白名单**（B4）：`SENSITIVE_TOOLS`（`:50`，读 env，默认 `search_tool`）· `needs_approval()`（`:112`）· `validate_approval_config()`（`:55`，启动自检，空名单直接 `raise`）

## 🟡 做到哪 / 缺什么

- ⚠️ **哪套 Agent 是"产品版本"——【未裁】**（属 **M5 的代际收敛**，见下）
- ✅ ~~**触发条件口径是错的**~~ ⇒ **2026-10-03 起【已修】**（B4）：`should_continue`（`:122`）现在是**三条路**（`approval` / `tools` / `END`），只有命中白名单才停
- ✅ ~~**零测试覆盖**~~ ⇒ **2026-10-03 起有 `api/test_approval_trigger.py`**（7 例，纯离线）。⚠️ **覆盖范围只有审批触发条件** —— **图的其余部分（节点行为 / 状态流转）仍无测试**
- ✅ ~~**`B5` 未做**~~ ⇒ **2026-10-03 起【已做】**（`②` Task 2）：待接管队列在 **`api/pending_approvals.py`**，出口是 **`GET /agent/pending`**（`api_v1_agent.py`）。📄 见 **`docs/specs/pending_approvals.md`**<br>⚠️ **但队列【不在这个模块里】** —— `agent_graph.py` 只负责"停下来"；"谁停下来了、从哪儿看"是 `api_v1_agent.py` 记账。⛔ 别在本模块找队列
- ⬜ **`B6` 未做** —— 接管之后**没有"改写后继续跑"**（批完就是终点）
- ⚠️ **DuckDuckGo 本机不通**（`search_tools.py:48` 注明实测 `duckduckgo.com` 完全不通）⇒ 这条链上的搜索会失败

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「这是个产品功能」 | 🟡 **它是 6 套并存实现之一** —— 另 5 套：`agent_checkpointer` · `agent_graph_advanced` · `agent_graph_advanced_learning` · `/ws/agent` 的内联 Executor · `plan_execute`。<br>🔴 **哪套留下【未裁】**（`docs/CODE_INVENTORY.md` §7 明说「2 代与 3 代的先后顺序**从代码判不出**」） |
| 「有 `tool_calls` ⇒ 停在审批」 | 🔴 **2026-10-03（B4）起【不再】** —— 只有命中 `SENSITIVE_TOOLS` 才停（`should_continue`，`:122`）；**非敏感工具直接跑完**，无人值守。⚠️ **`api/test_agent_repairs.py:533` 与 `api_v1_agent.py:66` 的旧注释就在说这条**，已同步更正 |
| 「白名单 = 危险工具清单」 | ⚠️ **不是** —— 第一版只有 `search_tool`（**外发数据**）。⚠️ **而 `calculator` 用的是 `eval(expression)`（`:27`）= 任意代码执行，它【不在】白名单里** ⇒ **无人值守直接跑**。📌 **这是 2026-10-03 发现的、尚未裁决的问题**（`eval` 的输入来自 LLM，LLM 的输入来自用户） |
| 「`.env` 里设了 `SENSITIVE_TOOLS`」 | ⚠️ **设不设都能跑** —— 不设走**默认值 `search_tool`**（`:51`）。⇒ 想加/减**必须显式改 `.env`**；⚠️ **改成空**会让服务**启动就炸**（`validate_approval_config`，`:55`） |
| 「审批是"全都接管"」 | 🔴 **不是** —— 硬门 D 要的是「**该被接管时被接管**」。改前"问个日期也停"那条路**验收过不去** |
| 「搜索工具是真抓取」 | 🔴 **不是** —— 这里是**旧的 DuckDuckGo**；**新一代真抓取**（`search_tools.py` 的 `web_search`）**只接在 MCP 与 learning 版上** |

## 关联

`DEC-018`（Agent 目录处置）· **`DEC-048`（审批触发条件改工具白名单 —— 本模块 2026-10-03 那次改动的决策前提）** ·
`ROADMAP` 待办 `T4`/`T5` · `docs/原理/架构.md` §1.3 ·
`后端补齐清单` **B4**（硬门 D 触发条件）· **`docs/specs/pending_approvals.md`**（`B5` 队列 —— ⚠️ **队列不本模块里**）·
`docs/specs/api_v1_agent.md` 的「实施计划 ②」
