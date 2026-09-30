# `api/agent_graph_advanced.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用，且是生产链** —— 但 🔴 **有两处实锤缺陷**（见下）<br>🔵 **改造中**：`B7` 要动它的 `llm`（`:39`，现在**没有 `max_tokens`**） |
| **对外提供** | `build_mcp_agent()`（返回编译好的图，`:288`）· `mcp_session()` · `get_mcp_tools()` · `call_mcp_tool_with_cache()` |
| **谁在用** | `api_v1_agent.py:450` 的 `POST /agent/mcp_chat`（**三代 Agent**） |
| **规模** | 400 行 |

## ✅ 做了什么

- **三代 Agent 图**：`agent_decide` →（有 tool_calls）→ `tool_execute` → 回 `agent`；(无) → `chat_node` → `END`
- **工具走 MCP Client**：`mcp_session()`（`:117`）**单 task 自开自关** —— ⚠️ 会话池**已移除**，理由写在 `:83-105`
- **工具调用缓存**：`call_mcp_tool_with_cache`（`:185`）· `CACHE_TTL_MAP`（`:169`）按工具分档；`execute_python` TTL=0（不缓存）
- **长期记忆注入**：`inject_memories_to_prompt`（`:48`）—— 从 mem0 检索后拼到 system prompt 前
- **轨迹**：`record_tool_start` / `record_tool_end` / `record_agent_decision`（`:223` 导入）
- **⭐ 多级预算**：`tool_execute` 里调 `check_multilevel_budget`（`:239`）—— **这是全仓【唯一】的调用点**

## 🟡 做到哪 / 缺什么

- 🔴 **记账用错单价**（见 ⚠️②）—— 本 spec 新查出
- 🔴 **超预算是软拦截**（见 ⚠️③）—— 上游文档已记，本 spec 确认落点
- ⚠️ **`llm` 没有 `timeout` / `max_retries`**（`:39-44`）：`ChatOpenAI` 吃 SDK 默认
  ⇒ 最坏 `600s × (1+2)`。⚠️ 同一类问题 `plan_execute.py` **已经修过**（显式设 30/20/15 + `max_retries=1`），**这里没修**
- ⚠️ `check_token_budget(user_name, estimated_tokens=500)` 的 **500 硬编码**，且 **`agent_decide` 与 `chat_node` 各查一次**
- ⚠️ `MemorySaver()`（`:397`）**进程内存** ⇒ 重启即丢（与 `/agent/langgraph_chat` 同）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **① 这是"进阶示例"** | ⛔ **它是生产实现** —— 模块 docstring 第 2 行写着「LangGraph **进阶示例**」，<br>但它就是 **`POST /agent/mcp_chat`（三代 Agent）的图本体**。<br>📌 **`agent_graph.py` 的 docstring 反而老老实实**。名字与自述**都不可信**，**看谁 import 它**。 |
| 🔴 **② 记账记的是实际模型** | ⛔ **不是 —— `model=` 写死成 `"qwen-turbo"`**（`:316` `:364`），而 `.env` 里实际是 `deepseek-v4-flash`。<br>**完整影响链**（已逐环核实）：<br>`record_usage(model="qwen-turbo")` ⇒ `PRICING.get("qwen-turbo")` = 0.003/0.006<br>⇒ 写进 `token_usage_logs.cost` 的是**按 qwen-turbo 单价算的钱**<br>⇒ `get_thread_cost()`（`:702`）`SELECT SUM(cost) … WHERE thread_id=%s`<br>⇒ **`check_multilevel_budget` 第二级 `MAX_THREAD_COST`（单位【元】）拿它比**<br>⇒ 🔴 **连"单次/单线程花费上限"这个拦截都是拿错的数在判。**<br>📌 ⚠️ **`PRICING` 表里【根本没有 `deepseek` 条目】**（实测）⇒ 这条路永远走不到正确的价。<br>✅ **对照**：`plan_execute.py:154` 用的是 `getattr(llm, "model_name", …)`（**从对象取，对的**）；`embedding_client.py:32` 也对。<br>⇒ **同一个仓里两种写法，一个对一个错** —— 错的 3 处是 `agent_graph_advanced.py:316/364` + **`agent_checkpointer.py:58`**。<br>🔴 **token 数是对的**（`usage.input_tokens` 是真的）⇒ **错的只有【钱】那一维**。 |
| 🔴 **③ 超预算会被拒** | ⛔ **不会 —— 是【软拦截】**（`:244-251`）：超预算时**塞一条 `ToolMessage` 文本提示**，<br>**HTTP 仍是 200**，只有 **LLM 自己能看到**那句"⚠️ 预算拦截" ⇒ **调用方在响应里看不出"被拒了"**。<br>📌 唯一的**硬拒绝**是该端点上的依赖 `check_budget`（`api_v1_agent.py:423-433`，抛 `AppException(QUOTA_EXCEEDED)`）——<br>⚠️ **但它判的是【用户每日 token 预算】，不是这一条**。<br>⇒ **"预算拦住了"这句话，在这个文件里只对 LLM 成立。** |
| ⚠️ **④ `should_continue` 跟 `agent_graph.py` 里那个是一回事** | ⛔ **不是** —— 本文件的是一个**内嵌在 `build_mcp_agent()` 里的局部函数**（`:377`），<br>返回值是 **`"tools"` / `"chat"`**；而 `agent_graph.py:95` 那个返回 **`"approval"` / `"tools"` / `END`**。<br>**同名、不同语义、不同作用域。** ⚠️ 搜 `should_continue` 会同时命中两个。 |
| ⚠️ **⑤ 「MCP 会话是池化的」** | ⛔ **池化已移除**（2026-09-20）—— 但文件里**同时留着"曾经的方案是全局单例"那段叙述**（`:76-78`）<br>和"会话池已移除"的说明（`:83-105`）。**读开头那几行容易读成当前实现。**<br>✅ 现状：**谁调用，谁在自己 task 内开关**（`:117` `mcp_session`）。 |
| ⚠️ **⑥ `model="qwen-turbo"` 是"用了便宜的模型"** | ⛔ **那只是记账时的标签，不影响真调用** —— 真模型是 `llm`（`:39`，取 `LLM_MODEL_CHAT`）。<br>⇒ **改那个字符串不会让服务换模型，只会改【单价口径】**。 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/api_v1_agent.md` | **唯一入口** `POST /agent/mcp_chat` |
| `docs/specs/token_tracker.md` | `PRICING` / `check_multilevel_budget` / `get_thread_cost` 的本尊 · **计划 ①a 的 Task 2 要扩 `PRICING`** |
| `docs/specs/plan_execute.md` | ⚠️ **同一个"漏传 / 写死"家族的对照**（那边超时都显式设了） |
| `docs/specs/pending_approvals.md`（待建） | 三代图**没有审批中断**（与 `/agent/langgraph_chat` 不同） |
| `后端补齐清单` **B7** | `llm`（`:39`）要接 `MAX_TOKENS_AGENT` |
| `后端补齐清单` **B13** | ⚠️ **R4「成本可见」就建立在本条 ⚠️② 之上** ⇒ **不修单价，看板上的钱就是错的** |
| `docs/decisions/DEC-017` | MCP transport 的选型（HTTP/SSE 那条路） |

> ### ✅ 要不要做 —— **2026-09-30 业务方全部裁定**
>
> | # | 事 | 裁定 | 落点 / 注意 |
> |---|---|---|---|
> | **1** | 🔴 **修 3 处 `model="qwen-turbo"` 硬编码** | ✅ **修** | `agent_graph_advanced.py:316` · `:364` · **`agent_checkpointer.py:58`**<br>⇒ 改成 **`getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")`**（**照抄 `plan_execute.py:154`**，别自己写） |
> | **2** | 🔴 **`PRICING` 表补 `deepseek` 条目** | ✅ **补** | 落点：`token_config.py` 的 `MODEL_PRICING`（**①a 的 Task 2 会建它** ⇒ 并进那一批）<br>⚠️ **必须与 #1 同批** —— 只修 #1 不补价 ⇒ 落到 `_DEFAULT_PRICING` 兜底价 ⇒ **比"明确配一个"更糟**（看不出来是兜底）<br>⬜ **具体单价待填**（`deepseek-v4-flash` 的实际价） |
> | **3** | ⚠️ **`llm` 补 `timeout` / `max_retries`** | ✅ **补** | 照 `plan_execute.py:70-76` 那三个常量的**做法**（`timeout=` + `max_retries=1`）<br>⬜ **具体秒数待定** —— 这是**多轮对话**，比 `plan_execute` 的单步长 ⇒ **别直接抄 30/20/15** |
> | **4** | ⚠️ **软拦截 → 硬拦截** | ✅ **要变成硬拦截** | 现在 `:244-251` 是塞 `ToolMessage` 文本、**HTTP 200** ⇒ 改成**抛 `AppException(QUOTA_EXCEEDED)`**<br>⚠️ **注意层次**：本文件在**图节点里**（不是路由层）⇒ 抛出的异常要能被**端点层**接住并转成 `AppException`（参照 `api_v1_agent.py:209` 接 `BudgetExceededError` 的写法）<br>⚠️ **改硬拦截会改变 `/agent/mcp_chat` 的响应形状** ⇒ 测试要一起改 |
