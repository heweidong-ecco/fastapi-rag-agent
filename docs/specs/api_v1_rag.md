# `api/api_v1_rag.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用** —— 有 3 条是"模拟类测试"<br>✅ 2026-10-01：两处 `ChatOpenAI`（`:566` 流式答案 · `:730` WS agent）接上 `MAX_TOKENS_ANSWER`（`B7`） |
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

## 关联

`后端补齐清单` **B1/B2/B3** · `docs/契约/接口契约.md` §四 · `docs/原理/架构.md` §3.2 ·
`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
