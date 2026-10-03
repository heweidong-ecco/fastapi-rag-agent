# `api/agent_checkpointer.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **地基在，但零测试 · 且有一处忽略配置**（117 → **121 行**，2026-10-03 `DEC-051`）<br>⚠️ **行数口径**：用 `scripts/spec_status.sh` 的数（= **真实行数**）。`wc -l` 对本文件**少算 1**（末行没有换行符）⇒ 两边会差 1，⛔ **不是笔误**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：该 `llm`（现于 `:21`）**改走 `llm_factory.make_llm("fast", "agent")`** —— `model`/`api_key`/`base_url`/`max_tokens` 不再写在本地。⚠️ `:39` 的 `bind_tools`（现于 `:42`）与 `:55` 的 `model_name`（**记账**）是**返回值必须是裸 `ChatOpenAI`** 的原因之一<br>✅ **2026-10-03（`DEC-049`）：`calculator` 的 `eval(expression)` 换成 `safe_math.calculate`**（`:28`；新增 import 在 `:17`）。⚠️ **本模块的 `calculator` 是活的** —— 走 `/agent/memory_chat` 那条链<br>🔴 **2026-10-03（`DEC-051`）：两处修掉** —— ① `tool_execute`（`:66`）改成**查 `TOOLS_BY_NAME` 表**分派（改前判 `if tool_name == "search"`、而真名是 `duckduckgo_search` ⇒ **搜索永远落 `else`**）；② 搜索工具换成 `search_tools.web_search`（`tools` 在 `:37`，表在 `:41`）。⚠️ **本模块的分派 bug 是"第二处现场"**（第一处在 `agent_graph.py`），且这条是**活路径**（`POST /agent/memory_chat`）。📄 `DEC-051` |
| **对外提供** | `build_checkpointer_agent()` · `checkpointer_agent` |
| **谁在用** | `api_v1_agent.py` → 路由 **`/agent/memory_chat`**（含 `check_session_token_budget` / `circuit` 两道门 + `session_key` 拼键）<br>🆕 `/agent/approve` —— **按登记表里的 `graph` 字段**路由到本图续跑（丙段） |

## ✅ 做了什么

- LangGraph Agent + **状态持久化**：`MemorySaver`（默认）/ `SqliteSaver`（`AGENT_CHECKPOINT_BACKEND=sqlite`）
- ⭐ **它是硬门 D（人工接管）的地基** —— `docs/现状核对` 判定「**地基是真的**」
- 🆕 **2026-10-03（`DEC-056` 丙段）**：**接上人工审批门** ——
  新增 `approval` 节点 + `interrupt_before=["approval"]`，路由改成**三路**
  （`should_continue`：含敏感工具 ⇒ `"approval"` / 只有本地工具 ⇒ `"tools"` / 无调用 ⇒ `END`）。
  ⚠️ **语义从 `agent_graph` 引入，⛔ 不是复制** —— 见「看代码会误判」第 2 行
- 工具与 `agent_graph.py` 同款：**`web_search`**（`:37`）· 计算器（**求值走 `safe_math`**）· 日期
  · ⭐ **工具名只有 `tools` 一个来源** —— `TOOLS_BY_NAME`（`:41`），`tool_execute`（`:66`）查它

## 🟡 做到哪 / 缺什么

- 🆕 ✅ **有测试了**（2026-10-03 丙段）：`api/test_memory_chat_approval.py` ——
  **审批门端到端**（真编图、真走 `should_continue`，只有 LLM 是假的 ⇒ 不联网）
  · ⚠️ 覆盖面**只有审批门那一块**，其余仍是 `docs/说明/测试.md` §六 **#3** 的"零覆盖"
- 🔴 **`backend=="redis"` 分支忽略 `REDIS_URL`**（见下）
- ✅ ~~🔴 **`record_usage(model="qwen-turbo")` 与实际调用的模型不符**（`:58`）~~
  **2026-10-01 已修**（`🅗 S4` + `S5`）⇒ 改成 `getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")`
  （**照抄 `plan_execute.py:154`**）。✅ **同批已给 `MODEL_PRICING` 补上 `deepseek-v4-flash`** ——
  只改这里不补价会落到兜底价（**看不出来是兜底**）。
  📄 另两处在 `docs/specs/agent_graph_advanced.md` ⚠️②（`:316` `:364`）—— **三处已一起改**。
- ⚠️ **它也是 6 套 Agent 之一** —— 哪套是产品版本**【未裁】**（M5）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「这个模块跟 `agent_graph.py` 一样有审批」** | ✅ **2026-10-03（`DEC-056` 丙段）起【有】了** —— `build_checkpointer_agent()` 带 `interrupt_before=["approval"]`，路由/白名单**从 `agent_graph` 引入**（`SENSITIVE_TOOLS` / `should_continue` / `human_approval`，⛔ 不是抄一份）。<br>⚠️ **改之前是"没有"**：`DEC-051` §遗留·2 记的「同一个仓里，一条路停下等人批，另一条直接执行」**已就此关闭**。<br>🔴 **但续跑要配对**：停下来的会话在 `/agent/approve` 靠**登记表里的 `graph` 字段**路由到本图（业务方 2026-10-03 裁）—— ⛔ 只加门不改 approve，会话会**永远放行不了** |
| 🔴 **「`should_continue` 还是本文件自己那份」** | ⛔ **不是** —— 2026-10-03 起本文件**删掉了自己那份两路版本**，改用 `agent_graph` 的**三路**版本。⚠️ 理由：审批判据只能有**一处**，抄一份 = `DEC-051` 记的病根（两处实现、不一致时**不报错**）。⇒ ⛔ 别在本文件里"补一个本地版" |
| 「支持 Redis 后端」 | 🔴 **`:105-108` 把 `redis_url` 注释掉了，直接回落 `MemorySaver()`** ⇒ **写 `redis` 也拿不到 Redis 持久化**（进程重启即丢） |
| 「有检查点 ⇒ 对话能跨重启」 | 🔴 **默认 `memory` 是【内存态】** ⇒ **重启即丢**；只有显式设 `AGENT_CHECKPOINT_BACKEND=sqlite` 才落盘 |
| 「成本记账是准的」 | 🟡 **Token 口径准，金额【2026-10-01 起也准了】** —— 模型名已改为从对象取，且 `MODEL_PRICING` 已补 DeepSeek 条目（`🅗 S4`+`S5`）<br>⚠️ **但仍是"近似"** —— 单价**不区分缓存命中**（拿不到命中/未命中拆分）⇒ 按未命中价记 ⇒ **偏高估** |

## 关联

`ROADMAP` 待办 `T4` · `docs/说明/测试.md` §六 · `后端补齐清单` **B5/B6**（硬门 D 队列与续跑）·
**`DEC-051`**（工具名分派勘误 —— 本模块是**第二处现场**）·
**`DEC-056` 丙段**（审批门 + `/agent/approve` 按图路由）·
`docs/specs/agent_graph.md`（同款工具与分派表的出处 —— **审批语义也从它引入**）·
`docs/specs/pending_approvals.md`（**停下来的那个会话记在哪**）·
`docs/specs/session_key.md`（**checkpoint 键怎么拼**）
