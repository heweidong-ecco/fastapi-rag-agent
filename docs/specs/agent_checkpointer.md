# `api/agent_checkpointer.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **地基在，但零测试 · 且有一处忽略配置**<br>✅ 2026-10-01：`llm`（`:21`）接上 `MAX_TOKENS_AGENT`（`B7`） |
| **对外提供** | `build_checkpointer_agent()` · `checkpointer_agent` |
| **谁在用** | `api_v1_agent.py:17` → 路由 **`/agent/memory_chat`** |

## ✅ 做了什么

- LangGraph Agent + **状态持久化**：`MemorySaver`（默认）/ `SqliteSaver`（`AGENT_CHECKPOINT_BACKEND=sqlite`）
- ⭐ **它是硬门 D（人工接管）的地基** —— `docs/现状核对` 判定「**地基是真的**」
- 工具与 `agent_graph.py` 同款：DuckDuckGo · 计算器 · 日期

## 🟡 做到哪 / 缺什么

- 🔴 **零测试覆盖**（`docs/说明/测试.md` §六 **#3**）
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
| 「支持 Redis 后端」 | 🔴 **`:108-112` 把 `redis_url` 注释掉了，直接回落 `MemorySaver()`** ⇒ **写 `redis` 也拿不到 Redis 持久化**（进程重启即丢） |
| 「有检查点 ⇒ 对话能跨重启」 | 🔴 **默认 `memory` 是【内存态】** ⇒ **重启即丢**；只有显式设 `AGENT_CHECKPOINT_BACKEND=sqlite` 才落盘 |
| 「成本记账是准的」 | 🟡 **Token 口径准，金额【2026-10-01 起也准了】** —— 模型名已改为从对象取，且 `MODEL_PRICING` 已补 DeepSeek 条目（`🅗 S4`+`S5`）<br>⚠️ **但仍是"近似"** —— 单价**不区分缓存命中**（拿不到命中/未命中拆分）⇒ 按未命中价记 ⇒ **偏高估** |

## 关联

`ROADMAP` 待办 `T4` · `docs/说明/测试.md` §六 · `后端补齐清单` **B5/B6**（硬门 D 队列与续跑）
