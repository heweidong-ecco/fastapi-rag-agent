# `api/api_v1_rag.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用** —— 有 3 条是"模拟类测试"<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：`/rag/stream_search` 的**取消传播做完了** —— 上游改 `astream`、`finally` 里 `aclose()` 关流、取消时记 `stream_cancelled_total`（`DEC-052`）。⚠️ **"上游真停"仍只有代码内证据**（本机无出账）<br>✅ 2026-10-01：两处 `ChatOpenAI`（现 `:578` 流式答案 · `:751` WS agent）接上 `MAX_TOKENS_ANSWER`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：那两处**改走 `llm_factory.make_llm("chat", "answer")`** ⇒ **本文件已不再 import `ChatOpenAI` / `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_CHAT`**。<br>⚠️ **`get_llm_stream()` 的惰性没变**（`make_llm` 自己把 langchain 的 import 关在函数内）· ⚠️ `temperature=0.3` + `streaming=True` 是**本处特有的逐点调参**，仍写在调用点上 |
| **对外提供** | **15 条 HTTP**（文档管理 4 · 检索 6 · 流式 1 · 模拟 3）· **2 条 WebSocket** |
| **谁在用** | 全部对外检索入口 |

## ✅ 做了什么

| 组 | 端点 |
|---|---|
| 文档管理 | `/rag/insert` · `/rag/insert_batch` · `/rag/upload_document` · **`DELETE /rag/documents/{doc_id}`** |
| 检索 | `/rag/pg_search` · `/rag/hybrid_search` · `/rag/rerank_search` · `/rag/rewrite_search` · `/rag/search` · `/rag/jwt_ask` |
| **流式** | **`/rag/stream_search`**（`:687`）—— ⚠️ **"全仓唯一 SSE 端点"这句 2026-10-03 起失效**：Agent 端已有第二条（`POST /agent/langgraph_chat/stream` · `DEC-050`） |
| WebSocket | `/ws/agent` · `/ws/test` |

## 🟡 做到哪 / 缺什么

- ✅ ~~**硬门 C（服务端 cancel）没做** —— 只有 `except asyncio.CancelledError`（旧 `:676`），**不关上游 HTTP 流**~~
  ⇒ **2026-10-03（`③` Task 5 · `B2`）已做**：上游 `astream`（`:691`）· `finally` 关流（`:733`）·
  取消记 `stream_cancelled_total`（`:735-738`）。📄 `DEC-052`
  ⚠️ **仍未证的是"上游计费真停"** —— 本机没有 DashScope 出账，⛔ 别把"我们关了流"说成"账单停了"
- ⬜ **无停止按钮**（前端不存在）
- 🟡 ~~零测试覆盖本文件（`docs/说明/测试.md` §六）~~ ⇒ **2026-10-03 起有了第一条**：
  `api/test_cancel_propagation.py`（10 例）覆盖 **`/rag/stream_search` 的取消路径**（`DEC-052`）。
  ⚠️ **但只盖了取消这一条路** —— 检索 / 引用 / 历史落库**仍然零覆盖**

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「15 条端点都是正经功能」 | 🔴 **其中 3 条是"模拟类测试"**：<br>· `/rag/ask`（`:832`）—— 是 **`tags=["模拟类测试"]` 的桩**，**直接 SQL 取 `documents` 原始行返回，没有 `answer` 字段**<br>· `/rag/async_ask` · `/rag/parallel_ask` —— **返回假文档**（`asyncio.sleep(2)` 后返回 3 条硬编码串） |
| 「`/rag/stream_search` 带真中断」 | ✅ **2026-10-03 起【成立】**（`③` Task 5 · `B2`）—— 客户端断开 ⇒ 取消传给生成器 ⇒ 关上游流。⚠️ 之前写这句是**错的**（`CLAUDE.md`/`README` 都写过）。<br>⚠️ **但"真中断"≠"账单停了"** —— 本机看不到上游出账（`DEC-052` §遗留·2） |
| 🔴 **「自己去 `request.is_disconnected()` 轮询才知道客户端断了」** | ⛔ **不用，那是框架给的** —— uvicorn 报 `spec_version 2.3` ⇒ Starlette 已监听 `http.disconnect` 并**取消生成器**。<br>⇒ 真正的缺口只有「**停下并关掉上游**」这一件。**自己加轮询 = 多余，且会掩盖真缺口**（`DEC-052`） |
| 🔴 **「中间件日志里那个秒数 = 生成耗时」** | ⛔ **不是** —— 它记到**响应开始返回**为止。实测：`(0.019s)` 的那条客户端收了 **27KB**、`(0.004s)` 的那条 **3 秒后**才 cancel。<br>⇒ ⛔ **别拿它当"生成提前停了"的证据**（第一版就这么误读过 · `DEC-052` §真服务实测） |
| 🔴 **「换两个字问同一个问题就能测取消」** | ⛔ **会被语义缓存吃掉** —— 问句只差"基线/切断"⇒ 当成同一个问题、`0.006s` 返回全量 ⇒ **根本没在生成，取消测不出来**。<br>⇒ 测取消**必须换语义上不同的问句** |
| 「`/rag/search` 是纯检索」 | 🟡 **它能生成答案** —— 传 `generate_answer: true` 即可（**默认 `False`**，`api/schemas.py:14`） |
| 「检索都走 `rag_pipeline`」 | 🔴 **`/rag/stream_search` 是内联裸 SQL**（`:581-590`）—— **不走 pipeline / hybrid_search / BM25 / reranker** ⇒ **与 `/rag/search` 召回不同源** |
| 🔴 **「本文件的端点都接了会话上限」** | ⛔ **不是** —— **只有 2 条接**（B8 · 2026-10-01）：`/rag/stream_search` 与 `/ws/agent`。<br>**`/rag/ask` · `/rag/jwt_ask` · `/rag/async_ask` · `/rag/parallel_ask` 【故意不接】** —— 它们**不调 LLM**（前两条只 `SELECT documents`，后两条是 mock）⇒ 接上去会让**没花钱的接口占额度**。<br>⚠️ 这条有**双向守卫**：`api/test_session_budget_wiring.py` 既查该接的接了，也查**不该接的没接** |
| ⚠️ **「`/rag/stream_search` 一直有 `thread_id`」** | 🔴 **2026-10-01 才补的**（B8，query 参数）。`QuestionRequest` **没有**这个字段 ⇒ 它**不在 body 里** |
| 🔴 **「`/ws/agent` 的额度是按人算的」** | ⛔ **按连接算** —— 该 WS **整条没有鉴权**，拿不到用户身份 ⇒ `user_name` 只能是 `"unknown"`，会话 id 用**每连接生成的 uuid**。<br>⇒ **断开重连 = 换一个新桶**。⚠️ 这不是漏洞：**没有身份就谈不上按人计**；根因（WS 无鉴权）记在 `DEC-041` 遗留·1 |

## 关联

`后端补齐清单` **B1/B2/B3** · `docs/decisions/DEC-052-取消传播的观测对象与上游改异步.md` ·
`docs/契约/接口契约.md` §四 · `docs/原理/架构.md` §3.2 ·
`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
