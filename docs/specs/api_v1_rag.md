# `api/api_v1_rag.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用** —— 有 3 条是"模拟类测试"<br>✅ 2026-10-01：两处 `ChatOpenAI`（现 `:578` 流式答案 · `:751` WS agent）接上 `MAX_TOKENS_ANSWER`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：那两处**改走 `llm_factory.make_llm("chat", "answer")`** ⇒ **本文件已不再 import `ChatOpenAI` / `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_CHAT`**。<br>⚠️ **`get_llm_stream()` 的惰性没变**（`make_llm` 自己把 langchain 的 import 关在函数内）· ⚠️ `temperature=0.3` + `streaming=True` 是**本处特有的逐点调参**，仍写在调用点上 |
| **对外提供** | **15 条 HTTP**（文档管理 4 · 检索 6 · 流式 1 · 模拟 3）· **2 条 WebSocket** |
| **谁在用** | 全部对外检索入口 |

## ✅ 做了什么

| 组 | 端点 |
|---|---|
| 文档管理 | `/rag/insert` · `/rag/insert_batch` · `/rag/upload_document` · **`DELETE /rag/documents/{doc_id}`** |
| 检索 | `/rag/pg_search` · `/rag/hybrid_search` · `/rag/rerank_search` · `/rag/rewrite_search` · `/rag/search` · `/rag/jwt_ask` |
| **流式** | **`/rag/stream_search`** —— **全仓唯一 SSE 端点**（`:687`） |
| WebSocket | `/ws/agent` · `/ws/test` |

## 🟡 做到哪 / 缺什么

- ⬜ **硬门 C（服务端 cancel）没做** —— 只有 `except asyncio.CancelledError`（`:676`），**不关上游 HTTP 流**
- ⬜ **无停止按钮**（前端不存在）
- ⬜ 零测试覆盖本文件（`docs/说明/测试.md` §六）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「15 条端点都是正经功能」 | 🔴 **其中 3 条是"模拟类测试"**：<br>· `/rag/ask`（`:832`）—— 是 **`tags=["模拟类测试"]` 的桩**，**直接 SQL 取 `documents` 原始行返回，没有 `answer` 字段**<br>· `/rag/async_ask` · `/rag/parallel_ask` —— **返回假文档**（`asyncio.sleep(2)` 后返回 3 条硬编码串） |
| 「`/rag/stream_search` 带真中断」 | 🔴 **不成立** —— 见上「硬门 C」。⚠️ `CLAUDE.md`/`README` 都写过这句，**都是错的** |
| 「`/rag/search` 是纯检索」 | 🟡 **它能生成答案** —— 传 `generate_answer: true` 即可（**默认 `False`**，`api/schemas.py:14`） |
| 「检索都走 `rag_pipeline`」 | 🔴 **`/rag/stream_search` 是内联裸 SQL**（`:581-590`）—— **不走 pipeline / hybrid_search / BM25 / reranker** ⇒ **与 `/rag/search` 召回不同源** |
| 🔴 **「本文件的端点都接了会话上限」** | ⛔ **不是** —— **只有 2 条接**（B8 · 2026-10-01）：`/rag/stream_search` 与 `/ws/agent`。<br>**`/rag/ask` · `/rag/jwt_ask` · `/rag/async_ask` · `/rag/parallel_ask` 【故意不接】** —— 它们**不调 LLM**（前两条只 `SELECT documents`，后两条是 mock）⇒ 接上去会让**没花钱的接口占额度**。<br>⚠️ 这条有**双向守卫**：`api/test_session_budget_wiring.py` 既查该接的接了，也查**不该接的没接** |
| ⚠️ **「`/rag/stream_search` 一直有 `thread_id`」** | 🔴 **2026-10-01 才补的**（B8，query 参数）。`QuestionRequest` **没有**这个字段 ⇒ 它**不在 body 里** |
| 🔴 **「`/ws/agent` 的额度是按人算的」** | ⛔ **按连接算** —— 该 WS **整条没有鉴权**，拿不到用户身份 ⇒ `user_name` 只能是 `"unknown"`，会话 id 用**每连接生成的 uuid**。<br>⇒ **断开重连 = 换一个新桶**。⚠️ 这不是漏洞：**没有身份就谈不上按人计**；根因（WS 无鉴权）记在 `DEC-041` 遗留·1 |

## 关联

`后端补齐清单` **B1/B2/B3** · `docs/契约/接口契约.md` §四 · `docs/原理/架构.md` §3.2 ·
`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
