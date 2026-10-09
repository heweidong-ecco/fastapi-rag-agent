# `app/rag/embedding_client.py`

| 项 | 内容 |
|---|---|
| **状态** | ✅ **客户端已惰性构造**（2026-10-05 · 批 6 · `T1` · `DEC-082`） |
| **对外提供** | `get_embedding(text, model="text-embedding-v2")` |
| **谁在用** | 几乎所有检索/入库路径（经 `rag_pipeline` / `api_v1_rag` / `cache.warmup_cache` / `hybrid_search`） |

## ✅ 做了什么

- **全仓唯一的 embedding 调用点**，固定走 **阿里云百炼 DashScope `text-embedding-v2`**（1536 维）
- 内嵌 Redis 缓存查询（`cache.get_cached_embedding`）· 调完记 `token_tracker.record_usage`
- ✅ **客户端惰性构造**（`_client = None` + `_get_client()`）—— **`import` 期不再碰凭据**；
  缺 `DASHSCOPE_API_KEY` 时抛**点名那个变量**的 `EnvironmentError`（与 `config.validate_config` 同族）
- ✅ **有测试了**（原先零覆盖）：`app/tests/test_embedding_client_lazy.py`（3 条 · 全离线 · 进 CI）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「配置齐全就能跑」 | ✅ **现在成立了**。改前 🔴 **模块级 `OpenAI(api_key=DASHSCOPE_API_KEY, ...)`** —— `config.py:39` 的 `os.getenv` **无默认值** ⇒ 缺这一行时是 `None` ⇒ **构造期就抛 `OpenAIError`** ⇒ **整条 import 链崩**（任何 import 它的模块都起不来）。**2026-10-05 批 6 已修**（`T1` · `DEC-082`） |
| 「key 为空 = 会炸」 | 🟡 **要分清**：**变量缺失**（`None`）改前**构造期就炸**；**空字符串**（`DASHSCOPE_API_KEY=`）改前**构造得出来**、要到**请求时**才 401。改后两种都**在取客户端时**被同一句点名的错误拦住 |
| 「启动时 `validate_config()` 会先拦住缺 key」 | 🟡 **正常启动路径上确实会**（`DASHSCOPE_API_KEY` 是**必填**，`config.py:61`）；<br>⚠️ **但**：**测试 / 独立脚本 / 任何没走 `validate_config` 的入口** —— 改前报的是一句**难懂的 `OpenAIError`**（它提的 `OPENAI_API_KEY` 本仓根本不用），改后**点名 `DASHSCOPE_API_KEY`** |
| 「缓存命中时不需要客户端」 | 🔴 **不是了** —— `DEC-082 §🅓` 把取客户端放在**查缓存之前**（否则「同一句有时报错、有时不报」取决于缓存状态）。**这是一处有意为之的行为变更** |
| 「LLM 能换，Embedding 也能换」 | 🔴 **不能** —— **Embedding 写死 DashScope**（`base_url` 与模型名硬编码在模块里，⛔ 不是配置项）；LLM 那套 `LLM_*` 三键**只管生成/对话** |
| 「LLM 侧也一样修好了」 | ⛔ **没有** —— 同族的 `make_llm()` **仍在 import 期构造**，本批**只把「报什么」改对**（`DEC-082 §🅔`）。真惰性要动 3 张图的模块级 `llm` + `bind_tools`，**与 `DEC-044`「运行时可切」是同一件事**，⛔ 不单独立项 |

## 关联

`docs/decisions/DEC-082-缺key时点名而不是抛SDK通用话.md`（本批）· `docs/待办总表.md` §三 `T1`（**已销账**）·
`docs/契约/环境变量.md` §4（Embedding 与 LLM 不是同一家）· `app/core/llm_factory.py`（LLM 侧同族，只改了报错）
