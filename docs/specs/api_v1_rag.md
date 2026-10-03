# `api/api_v1_rag.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **部分可用** —— 有 3 条是"模拟类测试"<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：`/rag/stream_search` 的**取消传播做完了** —— 上游改 `astream`、`finally` 里 `aclose()` 关流、取消时记 `stream_cancelled_total`（`DEC-052`）。⚠️ **"上游真停"仍只有代码内证据**（本机无出账）<br>✅ **2026-10-03（`③` Task 6 · `B3`）**：中断后**那半截答案存进历史**（提问 + 半截 + `INTERRUPTED_SUFFIX` 标记，落 `finally` —— `DEC-053`）<br>🔴 **未修**：**本文件的 LLM 调用一处都不记账**（`grep -c record_usage api/api_v1_rag.py` ⇒ **0**）⇒ 见下方「做到哪」与 `DEC-053` §遗留·2<br>✅ 2026-10-01：两处 `ChatOpenAI`（现 `:578` 流式答案 · `:751` WS agent）接上 `MAX_TOKENS_ANSWER`（`B7`）<br>✅ 2026-10-02（`①b` Task 5）：那两处**改走 `llm_factory.make_llm("chat", "answer")`** ⇒ **本文件已不再 import `ChatOpenAI` / `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_CHAT`**。<br>⚠️ **`get_llm_stream()` 的惰性没变**（`make_llm` 自己把 langchain 的 import 关在函数内）· ⚠️ `temperature=0.3` + `streaming=True` 是**本处特有的逐点调参**，仍写在调用点上 |
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
- ✅ ~~**中断后那半截答案【直接丢】**（`DEC-052` §遗留·3 点的名）~~ ⇒ **2026-10-03（`③` Task 6 · `B3`）已改**：
  取消时**存**「提问 + 半截 + 中断标记」（`_persist_interrupted_turn`，`:594-608`；调用点 `:769`），落点是 `finally`。
  📄 `DEC-053`。⚠️ **`except Exception` 那条路仍然丢提问**（**有意**，见该 DEC §遗留·1）
- 🔴 **本文件的 LLM 调用【一处都不记账】** —— `grep -c record_usage api/api_v1_rag.py` ⇒ **0**
  （`/rag/stream_search` · `/rag/search?generate_answer=true` · `/rag/jwt_ask` · `/ws/agent` 四条都是）。
  真库佐证：`token_usage_logs` 里非 embedding 行**全库只有 6 行**，全是 2026-09-20 的 agent graph 运行。
  ⚠️ **取消场景补不了**（`llm_factory` 没开 `stream_usage` ⇒ 提前 `aclose()` 就永远收不到 usage 帧）
  ⇒ 已立进 `docs/待办总表.md`，**范围是成功路径**（`DEC-053` §遗留·2）
- 🟡 ~~零测试覆盖本文件（`docs/说明/测试.md` §六）~~ ⇒ **2026-10-03 起有了第一条**：
  `api/test_cancel_propagation.py`（**13 例**）覆盖 **`/rag/stream_search` 的取消路径**
  （关流 `DEC-052` + 半截答案 `DEC-053`）。
  ⚠️ **但只盖了取消这一条路** —— 检索 / 引用 / 历史落库**仍然零覆盖**

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「15 条端点都是正经功能」 | 🔴 **其中 3 条是"模拟类测试"**：<br>· `/rag/ask`（`:832`）—— 是 **`tags=["模拟类测试"]` 的桩**，**直接 SQL 取 `documents` 原始行返回，没有 `answer` 字段**<br>· `/rag/async_ask` · `/rag/parallel_ask` —— **返回假文档**（`asyncio.sleep(2)` 后返回 3 条硬编码串） |
| 「`/rag/stream_search` 带真中断」 | ✅ **2026-10-03 起【成立】**（`③` Task 5 · `B2`）—— 客户端断开 ⇒ 取消传给生成器 ⇒ 关上游流。⚠️ 之前写这句是**错的**（`CLAUDE.md`/`README` 都写过）。<br>⚠️ **但"真中断"≠"账单停了"** —— 本机看不到上游出账（`DEC-052` §遗留·2）。<br>🔴 **2026-10-03 更正**：这句**只在"早切"（还没吐字就断）时成立** —— 见下一行 |
| 🔴🔴 **「`finally` 里 `await stream.aclose()` 就等于"把上游关了"」** | ⛔ **不够** —— **二次投递的取消**会在下一个真实挂起点重投：`aclose()` 一挂起 ⇒ 抛 `CancelledError` ⇒ **`finally` 剩余部分整体作废**。<br>⚠️ **真服务实测（2026-10-03）**：「晚切」时计数 `2.0→2.0` ❌、**无 `[cancel]` 日志** ❌、半截 **0 条** ❌ —— 而**单测当时 13 条全绿**（假流的 `aclose()` 不抛）。<br>⚠️ **早切测不出来**：生成器**还没被推进过** ⇒ `aclose()` 不必真收尾 ⇒ **不挂起 ⇒ 打不断**。**只有「用户已经看到字再点停止」才露出来**（而那才是主场景）。<br>✅ **两条一起**（缺一不可）：① **同步**收尾（计数/日志/落盘）提到**任何 `await` 之前** · ② 关流包 `anyio.CancelScope(shield=True)`。<br>📌 判据（可打印）：`api/test_cancel_propagation.py` ⇒ **17 passed**；两条修法**各有一条用例独立钉住**（`…survives_interrupted_aclose` 钉 shield · `…lands_even_when_aclose_itself_fails` 钉顺序 —— 实测把关流挪回前面 ⇒ **只有后者变红**）<br>📄 `DEC-054` · 复盘 `docs/复盘/2026-10-03-单测全绿而真服务全废.md` |
| 🔴 **「自己去 `request.is_disconnected()` 轮询才知道客户端断了」** | ⛔ **不用，那是框架给的** —— uvicorn 报 `spec_version 2.3` ⇒ Starlette 已监听 `http.disconnect` 并**取消生成器**。<br>⇒ 真正的缺口只有「**停下并关掉上游**」这一件。**自己加轮询 = 多余，且会掩盖真缺口**（`DEC-052`） |
| 🔴 **「中间件日志里那个秒数 = 生成耗时」** | ⛔ **不是** —— 它记到**响应开始返回**为止。实测：`(0.019s)` 的那条客户端收了 **27KB**、`(0.004s)` 的那条 **3 秒后**才 cancel。<br>⇒ ⛔ **别拿它当"生成提前停了"的证据**（第一版就这么误读过 · `DEC-052` §真服务实测） |
| 🔴 **「换两个字问同一个问题就能测取消」** | ⛔ **会被语义缓存吃掉** —— 问句只差"基线/切断"⇒ 当成同一个问题、`0.006s` 返回全量 ⇒ **根本没在生成，取消测不出来**。<br>⇒ 测取消**必须换语义上不同的问句** |
| 🔴 **「历史里那条助手消息是完整回答」** | ⛔ **可能是半截**（`③` Task 6 · `B3` 起）—— 被中断的那轮存进去的答案**尾部带 `INTERRUPTED_SUFFIX`**（"…（本次回答被中断，以上为已生成部分）"）。<br>⇒ **读历史的人（人 / 模型 / 另一个脚本）必须看这个尾巴**，⛔ 别把半截当结论。⚠️ 这个尾巴是**故意**进 prompt 的：不标 ⇒ 模型会把断掉的话当成自己说完了（`DEC-053`） |
| 🔴 **「取消后用户那问句也没了，是设计如此」** | ⛔ **不是设计，是碰巧** —— 改动前 `append_chat_history(user, …)` 与答案写在同一段收尾代码里，取消先 `raise` ⇒ **两个一起丢**。<br>⇒ **2026-10-03（`B3`）已让取消路径成对写**（`DEC-053`）。⚠️ **`except Exception` 那条路【仍然丢】**（**有意留着**，属另一件事 —— 已立 `DEC-055`，⬜ 未实施） |
| 「`/rag/search` 是纯检索」 | 🟡 **它能生成答案** —— 传 `generate_answer: true` 即可（**默认 `False`**，`api/schemas.py:14`） |
| 「检索都走 `rag_pipeline`」 | 🔴 **`/rag/stream_search` 是内联裸 SQL**（`:581-590`）—— **不走 pipeline / hybrid_search / BM25 / reranker** ⇒ **与 `/rag/search` 召回不同源** |
| 🔴 **「本文件的端点都接了会话上限」** | ⛔ **不是** —— **只有 2 条接**（B8 · 2026-10-01）：`/rag/stream_search` 与 `/ws/agent`。<br>**`/rag/ask` · `/rag/jwt_ask` · `/rag/async_ask` · `/rag/parallel_ask` 【故意不接】** —— 它们**不调 LLM**（前两条只 `SELECT documents`，后两条是 mock）⇒ 接上去会让**没花钱的接口占额度**。<br>⚠️ 这条有**双向守卫**：`api/test_session_budget_wiring.py` 既查该接的接了，也查**不该接的没接** |
| ⚠️ **「`/rag/stream_search` 一直有 `thread_id`」** | 🔴 **2026-10-01 才补的**（B8，query 参数）。`QuestionRequest` **没有**这个字段 ⇒ 它**不在 body 里** |
| 🔴 **「`/ws/agent` 的额度是按人算的」** | ⛔ **按连接算** —— 该 WS **整条没有鉴权**，拿不到用户身份 ⇒ `user_name` 只能是 `"unknown"`，会话 id 用**每连接生成的 uuid**。<br>⇒ **断开重连 = 换一个新桶**。⚠️ 这不是漏洞：**没有身份就谈不上按人计**；根因（WS 无鉴权）记在 `DEC-041` 遗留·1 |

## 关联

`后端补齐清单` **B1/B2/B3** · `docs/decisions/DEC-052-取消传播的观测对象与上游改异步.md` ·
`docs/decisions/DEC-053-中断后的半截答案存进历史并打标记.md` ·
`docs/decisions/DEC-054-取消路径的收尾顺序与关流护盾.md` ·
`docs/decisions/DEC-055-中断与异常路径的留痕口径.md`（⬜ 未实施）·
`docs/契约/接口契约.md` §四 · `docs/原理/架构.md` §3.2 ·
`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
