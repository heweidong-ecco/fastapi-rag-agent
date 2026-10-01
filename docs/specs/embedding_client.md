# `api/embedding_client.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用，但有一处【启动崩溃】隐患**（`ROADMAP` 待办 **T1**） |
| **对外提供** | `get_embedding(text, model="text-embedding-v2")` |
| **谁在用** | 几乎所有检索/入库路径（经 `rag_pipeline` / `api_v1_rag` / `cache.warmup_cache`） |

## ✅ 做了什么

- **全仓唯一的 embedding 调用点**（`:15`），固定走 **阿里云百炼 DashScope `text-embedding-v2`**（1536 维）
- 内嵌 Redis 缓存查询（`cache.get_cached_embedding`）· 调完记 `token_tracker.record_usage`

## 🟡 做到哪 / 缺什么

- 🔴 **T1 未修**（见下）
- ⬜ 零测试覆盖
- 📌 **Embedding 不能换** —— `base_url` 与模型名**硬编码在 `:12-15`**，不是配置项

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「配置齐全就能跑」 | 🔴 **模块级 `OpenAI(api_key=DASHSCOPE_API_KEY, ...)`**（`:10-13`）——<br>**key 为空时构造期就抛 `OpenAIError`** ⇒ **整条 import 链崩**（任何 import 它的模块都起不来） |
| 「启动时 `validate_config()` 会先拦住缺 key」 | 🟡 **正常启动路径上确实会**（`DASHSCOPE_API_KEY` 是**必填**）；<br>⚠️ **但**：**测试 / 独立脚本 / 任何没走 `validate_config` 的入口** ⇒ **报的是一句难懂的 `OpenAIError`，而不是"缺 DASHSCOPE_API_KEY"** |
| 「LLM 能换，Embedding 也能换」 | 🔴 **不能** —— **Embedding 写死 DashScope**（LLM 那套 `LLM_*` 三键**只管生成/对话**） |

📌 **T1 是 `ROADMAP` 待办总账里【自标"优先级最高"】的一条** —— 修法：把模块级 `client` 改成**惰性构造**。

## 关联

`ROADMAP` 待办总账 **T1** · `docs/契约/环境变量.md` §4（Embedding 与 LLM 不是同一家）
