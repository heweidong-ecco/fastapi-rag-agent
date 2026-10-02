# `api/agent_graph.py`

| 项 | 内容 |
|---|---|
| **状态** | ⚰️ **遗留 / 未经裁决** —— **6 套 Agent 实现之一**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:20`）**改走 `llm_factory.make_llm("fast", "agent")`**。⚠️ **模型轴是 `fast`**（不是 chat）—— 这是改动前的实际取值，收口时**原样保留** |
| **对外提供** | 路由 `/agent/langgraph_chat` · `/agent/approve` |
| **谁在用** | `api_v1_agent.py:12`（`from agent_graph import agent_graph`） |

## ✅ 做了什么

- 基础 LangGraph Agent：`agent` 决策节点 → `tools` 执行循环
- 工具：**DuckDuckGo 搜索**（`DuckDuckGoSearchRun()`，`:43`）· 计算器 · 日期
- **人工审批**：`interrupt_before=["approval"]`（`:148`）+ `/agent/approve` 端点

## 🟡 做到哪 / 缺什么

- ⚠️ **哪套 Agent 是"产品版本"——【未裁】**（属 **M5 的代际收敛**，见下）
- 🔴 **触发条件口径是错的**（见下）
- ⬜ **零测试覆盖**
- ⚠️ **DuckDuckGo 本机不通**（`search_tools.py:48` 注明实测 `duckduckgo.com` 完全不通）⇒ 这条链上的搜索会失败

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「这是个产品功能」 | 🟡 **它是 6 套并存实现之一** —— 另 5 套：`agent_checkpointer` · `agent_graph_advanced` · `agent_graph_advanced_learning` · `/ws/agent` 的内联 Executor · `plan_execute`。<br>🔴 **哪套留下【未裁】**（`docs/CODE_INVENTORY.md` §7 明说「2 代与 3 代的先后顺序**从代码判不出**」） |
| 「审批是为了敏感操作」 | 🔴 **触发条件 = 任意 `tool_calls`**（`should_continue`，`:100-103`）⇒ **问一句"今天几号"也会进审批** |
| 「搜索工具是真抓取」 | 🔴 **不是** —— 这里是**旧的 DuckDuckGo**；**新一代真抓取**（`search_tools.py` 的 `web_search`）**只接在 MCP 与 learning 版上** |

## 关联

`DEC-018`（Agent 目录处置）· `ROADMAP` 待办 `T4`/`T5` · `docs/原理/架构.md` §1.3 ·
`后端补齐清单` **B4**（硬门 D 触发条件）
