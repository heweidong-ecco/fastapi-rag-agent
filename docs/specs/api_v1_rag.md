# `api/api_v1_rag.py`

| 项 | 内容 |
|---|---|
| **状态** | 🔴 **2026-10-05（`DEC-073`）：`/rag/search` 与 `/rag/rewrite_search` 补上 B8 + B11 两道闸**（`unified_search` `:534`/`:538` · `rewrite_search_api` `:480`/`:484`，各加 `thread_id: str = "default"`）—— **改前这两条链零闸**，而它们默认就真调 LLM。⚠️ **记账点不本文件**，在其下游（`rag_pipeline` / `answer_with_citations` / `query_rewriter`）；⛔ `/rag/stream_search` 仍不记账（流式 usage 拿不到）。<br>✅ **2026-10-04（`DEC-065`）：`tags=["模拟类测试"]` 整组【归零】** —— 另 **2 条**（`/rag/async_ask` · `/rag/parallel_ask`）**已删**（纯 mock · 零消费者）。本文件因此 **`@router.` 14 → 12**、**HTTP 12 → 10**。<br>⚠️ ⛔ **本文件现在没有任何"假端点"了** —— 剩下的 10 条 HTTP 条条都动真东西（库里/embedding/共享层）。<br>🔴 **2026-10-04（`DEC-064`）：`POST /rag/jwt_ask` 已【删除】** —— 三条理由与做法见 `docs/decisions/DEC-064-删除-rag-jwt-ask.md`。本文件因此 **`@router.` 15 → 14**、**HTTP 13 → 12**。<br>🟡 ~~部分可用 —— 有 2 条是"模拟类测试"（原 3 条；`/rag/ask` 2026-10-03 已删，`DEC-057`）~~ ⇒ **已归零**。<br>🔵 **2026-10-04（`B1` 剩余 4 条链 · 批 3）：`/rag/stream_search` 的 SSE 生成器【改成走共享层】** —— 内联的 `try/except/finally` 整段换成 `sse_response(sse_stream(...))`（`:731`）。<br>· 🔴 **行为必须【逐帧等价】，⛔ 不是"顺手统一"** ⇒ 三处**显式覆盖**骨架默认值：`ensure_ascii=True`（中文仍 `\uXXXX`）· `on_error`（**只有 error 帧、⛔ 不加 `[DONE]`**）· `chunk_delay=0.01`（限速照旧）。<br>· ⭐ **判据 = 既有两份用例"全绿且文件 diff 为空"**（`api/test_agent_sse.py` + `api/test_cancel_propagation.py`）—— ⛔ 没有新加断言 = 重构真的等价。<br>· ⚠️ **上游从同步 `.stream()` 改 `astream(messages)`（`:735`）不是本批的改动**（那是 `③` Task 5 · `B2`）；本批只是把它搬进 `lambda: …` 工厂。<br>📄 骨架见 `docs/specs/sse.md`<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：`/rag/stream_search` 的**取消传播做完了** —— 上游改 `astream`、`finally` 里 `aclose()` 关流、取消时记 `stream_cancelled_total`（`DEC-052`）。⚠️ **"上游真停"仍只有代码内证据**（本机无出账）<br>✅ **2026-10-03（`③` Task 6 · `B3`）**：中断后**那半截答案存进历史**（提问 + 半截 + `INTERRUPTED_SUFFIX` 标记，落 `finally` —— `DEC-053`）<br>✅ **2026-10-04（`DEC-055`）**：**三条出口都留痕，且各带一个 `status`** —— `done`（= 完整答案、⛔ 无标记）/ `cancelled` / `error`。🔴 改前 **`except Exception` 那条一个字都不留**（连提问一起丢）⇒ 现在也写了。留痕例程已收进 **`cache.persist_turn`**，本文件只剩**两个调用点**（`_complete` `:715` · `on_incomplete` `:745`）<br>🔴 ~~**未修**：**本文件的 LLM 调用一处都不记账**（`grep -c record_usage api/api_v1_rag.py` ⇒ **0**）⇒ 见下方「做到哪」与 `DEC-053` §遗留·2~~ ⇒ **2026-10-05（`DEC-073`）部分修复**：`/rag/search` 与 `/rag/rewrite_search` 两条链**记账点在下游模块**、闸在本文件；⛔ **`/rag/stream_search` 与两条 Agent 路径仍未修** ⇒ 见下方「做到哪」<br>✅ 2026-10-01：两处 `ChatOpenAI`（**当时** `:578` 流式答案 · `:751` WS agent）接上 `MAX_TOKENS_ANSWER`（`B7`）—— ⚠️ **两处都已不存在**：2026-10-02 起改走 `llm_factory.make_llm("chat","answer")`（见下一条），`ChatOpenAI` 早已不是本文件的调用形状<br>✅ 2026-10-02（`①b` Task 5）：那两处**改走 `llm_factory.make_llm("chat", "answer")`** ⇒ **本文件已不再 import `ChatOpenAI` / `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_CHAT`**。<br>⚠️ **`get_llm_stream()` 的惰性没变**（`make_llm` 自己把 langchain 的 import 关在函数内）· ⚠️ `temperature=0.3` + `streaming=True` 是**本处特有的逐点调参**，仍写在调用点上 |
| **对外提供** | **10 条 HTTP**（文档管理 4 · 检索 **5** · 流式 1 · ~~**模拟 2**~~ ⇒ **0**）· **1 条 WebSocket**<br>⚠️ **计数沿革**：14 →（2026-10-03）13 —— `/rag/ask` 已删（`DEC-057`）→（2026-10-04）**12** —— `/rag/jwt_ask` 已删（`DEC-064`）→（2026-10-04）**10** —— `/rag/async_ask` · `/rag/parallel_ask` 已删（`DEC-065`）→（2026-10-05）**11** —— **WS `/ws/test` 已删**（`DEC-075` §十）。<br>🔴 **顺带更正一个【改前就存在】的错**：本行原写「**15 条 HTTP**」，**而括号里的分项一直加不到 15**（4+6+1+3 = **14**）—— **分项是对的，那个 15 是错的**。判据（可打印）：`grep -c '@router\.' api/api_v1_rag.py` ⇒ **11**（= **10 HTTP + 1 WebSocket**，WS 那条在 `:883`）。📌 **这种"总数与分项对不上"的错，本仓已记过一次**（数出来的数要能对上）。<br>⚠️ **用 `grep -c '@router\.'` 数路由时：⚠️ 墓碑注释里⛔【别】写 `@router.` 字面串** —— 会把它一起数进去（`DEC-065` 实测：带 `@` ⇒ 14，去掉 ⇒ **12**）。📌 这就是判据纪律第 2 条「**注释里也有同样的串**」。<br>🔴 **2026-10-05 又踩了一次**（`DEC-075` §十）：删除 `/ws/test` 时墓碑注释写成了 `@router.websocket("/ws/test")` ⇒ 数出 **12**（应 11）。⚠️ **同一个坑、同一份文件、隔一天** —— ⇒ 墓碑一律写成 **`WS /ws/test`** 这种**不含 `@router.` 的形态**（本文件 `DEC-057` 那条墓碑本来就是这么写的）。 |
| **谁在用** | 全部对外检索入口 |

## ✅ 做了什么

| 组 | 端点 |
|---|---|
| 文档管理 | `/rag/insert` · `/rag/insert_batch` · `/rag/upload_document` · **`DELETE /rag/documents/{doc_id}`** |
| 检索 | `/rag/pg_search` · `/rag/hybrid_search` · `/rag/rerank_search` · `/rag/rewrite_search` · `/rag/search` |
| **流式** | **`/rag/stream_search`**（`stream_search`，`:603`）—— ⚠️ **"全仓唯一 SSE 端点"这句 2026-10-03 起失效**：Agent 端已有第二条（`POST /agent/langgraph_chat/stream` · `DEC-050`） |
| WebSocket | `/ws/agent`（⚠️ **2026-10-05 起要首帧认证** · `DEC-075`）<br>⚰️ `/ws/test` **已删**（`DEC-075` §十）—— 纯回声测试桩 · 消费者 = 0 |

## 🔴 2026-10-03 · 多用户隔离（`DEC-056` **甲段 + 乙段**）—— ✅ **8 条检索路径全部收口**（⚠️ 现存 **6 条**）

> ⚠️ **后续删了 2 条**：`/rag/ask` **2026-10-03** 删（`DEC-057`）· `/rag/jwt_ask` **2026-10-04** 删（`DEC-064`）
> ⇒ **现存的检索路径是 6 条**，**这 6 条全部收口**。
> 下表的「8 条」是**收口当时**的口径，保留以便对照（它确实一度是 8 条）。
> ⚠️ **本节结论 ⛔ 不因删端点而变** —— 删的是**已经收口好的**两条；**没有任何一条"没做"的被删掉冒充"做完了"**。

**「谁能看见谁的文档」已收口。** 做法是**共享层承重**（决策 5）——过滤写在
`db.search_similar` / `bm25_index.bm25_search`，⛔ 不是每个端点各写一遍。
⚠️ **但乙段那两条【不走共享层】**（自己写 SQL）⇒ 改共享层**碰不到它们**，只能各修各的。
⇒ **下面这张表按「是否走共享层」分成两组**，这就是本节的读法。

| 端点（函数名锚点 ⭐ 行号会漂） | 现状 | 怎么过滤的 |
|---|---|---|
| `/rag/pg_search`（`pg_search`） | ✅ **本来就对** | **自己写 SQL**，一直有 `WHERE requested_by = %s` |
| ~~`/rag/ask`~~（`ask_question`） | ⛔ **2026-10-03 已【删除】** | 见 `DEC-057` —— 它**同样是自己写 SQL**、**同样一直有 `WHERE`**，所以**删它与隔离无关**（隔离账里它从来不欠账）。🔴 本行原先把端点名写成 `WS /ws/agent` —— **错**（`WS /ws/agent` 整条**不碰 `documents`**，且（当时）**无鉴权**、身份写死 `"unknown"` —— ✅ 2026-10-05 `DEC-075` 这两条都已修） |
| `/rag/hybrid_search`（`hybrid_search_api`） | ✅ **甲段已收口** | `hybrid_search(…, user_id=user_name)` → 共享层 |
| `/rag/rerank_search`（`rerank_search_api`） | ✅ **甲段已收口** | `rerank_search(…, user_id=user_name)` → 共享层 |
| `/rag/rewrite_search`（`rewrite_search_api`） | ✅ **甲段已收口** | `hybrid_search_with_rewrite(…, user_id=user_name)` → 共享层 |
| `/rag/search`（`unified_search`） | ✅ **甲段已收口** | `pipeline.search_async(…, user_id=user_name)` → `db.search_similar` |
| ~~`/rag/jwt_ask`~~（`jwt_ask_question`） | ⛔ **2026-10-04 已【删除】** | 见 `DEC-064` —— 它**同样是自己写 SQL**（乙段给它补过 `WHERE requested_by = %s`），所以**删它与隔离无关**（隔离账里它从来不欠账）。⚠️ **⛔ 别读成"乙段那一下白做了"**：乙段那次收口**是对的、也有效的**；删它是**另一件事**（`LIMIT` 无 `ORDER BY` ⇒ 结果不可复现 + 能力已被 `/rag/pg_search` 覆盖） |
| `/rag/stream_search`（`stream_search`） | ✅ **乙段已收口** | **改成走共享层**：`search_similar(query_embedding, req.top_k, user_id=user_name)`（`:637`） |

⚠️ **乙段【没有】动的两件事**（⛔ 别读成"乙段全修好了"）—— **两条后来都作为独立事项结清了**：
* ~~**`/rag/jwt_ask` 拿到 `question` 却不拿它做检索**（无 embedding、无 `ORDER BY`）~~ ⇒ ⛔ **2026-10-04 连同端点一起删了**（`DEC-064`）——
  「**承诺检索**」与「**实际不检索**」的矛盾**不是被"修"好的，是那个矛盾的载体被删掉了**
  （这条端点全仓**无消费者**，删掉它没有任何人少一项能力）。
  ⚠️ **它当时不在隔离收口内** —— 乙段那次**只加 `WHERE`，⛔ 没动检索语义**，这话当时就写明了。
* ~~**`/rag/ask` 的定位**~~ ⇒ ✅ **2026-10-03 已删**（`DEC-057`）——
  它**读真库**却自称「模拟类测试」，`LIMIT` 无 `ORDER BY` ⇒ 结果不可复现；能力被 `/rag/pg_search` 覆盖、全仓无消费者。
  ⚠️ **删它⛔ 不是隔离的事** —— 它一直是按人过滤的（`WHERE requested_by`），**隔离账上它从来不欠**。

⚠️ **甲段 / 乙段都只动「检索」** —— 写入侧（`/rag/insert` · `/rag/insert_batch` · `/rag/upload_document`）
本来就把 `user_name` 写进 `requested_by`，**不属于 fail-open 那一类**。
（`DELETE /rag/documents/{doc_id}` 的**归属校验**是另一件事，记在 `DEC-056` §遗留。）

🔴 **检索侧【有意不给】admin 例外**（`DEC-056` §七 裁决 2 的文字 2026-10-03 已更正）——
已过滤的端点**对 admin 一视同仁**。⚠️ **今天看不出差别**（admin 拥有 100% 语料）。

📌 **判据（可打印）**：
* **用例** —— `POSTGRES_DB=rag_test venv/bin/python -m pytest api/test_isolation.py -q -m needs_db` ⇒ **9 passed**
  （全文件 `18 tests collected` = 离线 **9** + `needs_db` **9**）
* **静态** —— `grep -n 'WHERE requested_by' api/api_v1_rag.py | grep -v '#'` ⇒ **1 行**（`:415`）
  （只剩 `pg_search` —— **自己写 SQL 的读端点就剩这 1 条**；其余 **5** 条走共享层）
  ⚠️ **2026-10-03 由 3 变 2**（`/rag/ask` 删 · `DEC-057`）· **2026-10-04 由 2 变 1**（`/rag/jwt_ask` 删 · `DEC-064`）。
  ⚠️ **必须带 `| grep -v '#'`** —— 现在有**两行注释**里也含这个串（`DEC-056` 乙段加的 · `DEC-064` 墓碑加的；
  本仓判据纪律第 2 条：「批量替换后按位置核，⛔ 别只数替换了几处 —— **注释里也有同样的串**」）

## 🟡 做到哪 / 缺什么

- ✅ ~~**硬门 C（服务端 cancel）没做** —— 只有 `except asyncio.CancelledError`（旧 `:676`），**不关上游 HTTP 流**~~
  ⇒ **2026-10-03（`③` Task 5 · `B2`）已做**：上游 `astream`（现 `:735`）· 关流与计数**2026-10-04 起搬进
  共享层 `api/sse.py`**（约束①②：同步收尾排在 `await` 前 + `shield` 关上游）—— 本文件这边
  只剩一个 `on_incomplete` 回调（`:745`）。📄 `DEC-052` · `DEC-054` · `DEC-055`
  ⚠️ **仍未证的是"上游计费真停"** —— 本机没有 DashScope 出账，⛔ 别把"我们关了流"说成"账单停了"
- ⬜ **无停止按钮**（前端不存在）
- ✅ ~~**中断后那半截答案【直接丢】**（`DEC-052` §遗留·3 点的名）~~ ⇒ **2026-10-03（`③` Task 6 · `B3`）已改**：
  取消时**存**「提问 + 半截 + 中断标记」，落点由骨架排在 `await` 之前。📄 `DEC-053`
  · ⚠️ **`DEC-055` 搬了家**：`_persist_interrupted_turn`（原 `:608`）**已删**，逻辑收进
    **`cache.persist_turn`** —— 它与 5 条 Agent 链**共用同一段**（`DEC-055` 决策 2）。
  · ✅ ~~**`except Exception` 那条路仍然丢提问**（**有意**，`DEC-053` §遗留·1）~~
    ⇒ **2026-10-04（`DEC-055`）已改**：**异常出口也写了**（`status="error"`，同样带中断标记）。
    ⚠️ 这是 `DEC-053` §遗留·1 明确留给 `DEC-055` 的那一件，不是"顺手扩范围"
- 🔴 ~~**本文件的 LLM 调用【一处都不记账】**~~ ⇒ ✅ **2026-10-05 部分修复（`DEC-073`）**。
  ⚠️ **修复范围要说准**（⛔ 别读成"本文件全记上了"）：
  · ✅ **`/rag/search` 与 `/rag/rewrite_search` 现在有 B8 + B11 两道闸**
    （`unified_search` `:534`/`:538` · `rewrite_search_api` `:480`/`:484`，各带 `thread_id: str = "default"` 形参）；
  · ✅ **这两条链**上的 LLM 调用已记账 —— 但**记账点不在本文件**，在
    `rag_pipeline` / `answer_with_citations` / `query_rewriter`（本文件只把 `user_name` 递进去）；
  · ⛔ **`/rag/stream_search` 仍然不记账**（流式 usage 拿不到 ⇒ 需另开 `stream_usage` = 行为变更，见 §五 of `DEC-073`）；
  · ⛔ **`get_agent_executor` / `agent_websocket` 也不在本次范围**（Agent 侧，`DEC-072` 管）。
  ⚠️ **本文件里真正的 LLM 调用点**（`grep -n 'astream(\|ainvoke(\|make_llm(' api/api_v1_rag.py`）：
  `stream_search`（`:765`，那行 `get_llm_stream().astream(messages)`）· `get_agent_executor`（`:822`，被 Agent 端点共用）· `agent_websocket`（`:946`）。<br>⚠️ **后两个行号 2026-10-04（`DEC-066`）重取过** —— 本文件当天因收口 `calculator` 而位移（`get_agent_executor` 776→**777** · `agent_websocket` 831→**840**）。<br>🔴 **2026-10-05 又重取一次**：三个数**全都漂了**（735→**765** · 777→**822** · 840→**946**）—— 漂因是 `DEC-073`/`DEC-074`/`DEC-075` 几轮在本文件里加/删/改注释。⛔ **不是删 `/ws/test` 引起的**（那条在 `:968` 之后，改不到 946）。⇒ 判据仍是本行开头那条 `grep -n`，**别凭记忆补**。
  🔴 **2026-10-03 更正（乙段顺带核出）**：本行原先列的四条里有**两条是错的** ——
  · ~~**`/rag/jwt_ask` 一处 LLM 都不调**（`jwt_ask_question` 整条是 `SELECT content … LIMIT` 然后返回）~~
    —— ⛔ **该端点 2026-10-04 已整体删除**（`DEC-064`）；这里保留的是**当时核出的事实**（它现在不存在了）；
  · **`/rag/search?generate_answer=true` 的 LLM 调用不在本文件** —— 它在 `rag_pipeline` 里
    （本文件只 `pipeline.search_async(…)`）⇒ **那条账要记到 pipeline 头上，不是这里**。
  真库佐证（`DEC-073` 改动**前**）：`token_usage_logs` 里非 embedding 行**全库只有 6 行**，全是 2026-09-20 的 agent graph 运行。
  ⚠️ **取消场景补不了**（`llm_factory` 没开 `stream_usage` ⇒ 提前 `aclose()` 就永远收不到 usage 帧）
  ⇒ 已立进 `docs/待办总表.md`，**范围是成功路径**（`DEC-053` §遗留·2）
- 🟡 ~~零测试覆盖本文件（`docs/说明/测试.md` §六）~~ ⇒ **2026-10-03 起有了第一条**：
  `api/test_cancel_propagation.py`（**22 例**；其中 **RAG 15 · Agent 7**）覆盖 **`/rag/stream_search`
  的取消路径与异常路径**（关流 `DEC-052` + 半截答案 `DEC-053` + 三条出口各写什么 `status` `DEC-055`）。
  ⚠️ **覆盖仍偏在"非正常出口"上**：**检索 / 引用（`sources` 帧）** 只有零散几条；正常路径的**历史落库**
  现在有了（`test_rag_full_answer_is_saved_without_interrupt_marker`），但**检索语义本身仍然零覆盖**
- ✅ ~~**隔离：4 条收口 / 2 条没做**~~ ⇒ **2026-10-03（乙段）后：8 条检索路径全部收口**（`DEC-056` 甲段 + 乙段）。
  ⚠️ **2026-10-04 更正**：那 8 条里**已删 2 条**（`/rag/ask` · `DEC-057`；`/rag/jwt_ask` · `DEC-064`）
  ⇒ **现存 6 条，全部收口**（结论不变：删掉的这两条本来就是收口好的，⛔ 不是"没做的被删掉"）。
  `api/test_isolation.py` **18 条用例守着**（离线 **9** · `needs_db` **9**）。
  ⚠️ **2026-10-03 时是 19 条**（离线 9 · `needs_db` 10）—— 随 `/rag/jwt_ask` 删除少了那 1 条
  （`test_jwt_ask_endpoint_does_not_leak_across_users`：端点不存在了，用例没有可守的对象）。
  已做过证伪：**甲段**拿掉共享层 `WHERE` ⇒ **4 条变红**；**乙段**分别退回那两条的修改 ⇒ **各恰好 1 条红**。
  ⚠️ **乙段那两条不走共享层**（自己写 SQL）⇒ 它们的过滤**不在** `db.py` / `bm25_index.py` 里 ——
  **改共享层碰不到它们**，这是本节最该记住的一条。
  ⚠️ ~~「收口后召回会降」~~ —— **2026-10-03 更正：这句过头了**。非 admin 用户在那 6 条已收口的路径上
  **本来就只有 0 篇自己的文档** ⇒ 乙段是**消除不一致**，⛔ 不是新加一道限制。
  ✅ ~~**仍未修（且都不是隔离问题）**：`jwt_ask` 的「拿到 `question` 却不拿它做检索」~~ ⇒ **2026-10-04 端点整体删除**（`DEC-064`）⇒ 该项**已消账**。
  ⚠️ **说清楚是哪种消账**：那是**把矛盾体删掉了**，⛔ **不是"把它修成会检索了"** —— 见上方专节。
  ✅ **`/rag/ask` 的定位**已在 2026-10-03 由「已裁待删」变为**已删**（`DEC-057`）⇒ 该项已消账。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 「10 条端点都是正经功能」 | ✅ **2026-10-04（`DEC-065`）起【成立】** —— `tags=["模拟类测试"]` **整组归零**，剩下的**条条动真东西**。<br>🔴 **在此之前【不成立】，而且那是本仓栽过的一个坑**：该组一度有 **4 条**，其中 **2 条**（`/rag/async_ask` · `/rag/parallel_ask`）**返回假文档**（`asyncio.sleep(2)` 后 3 条硬编码串），另 **2 条**（`/rag/ask` · `/rag/jwt_ask`）**自述"模拟类"却读真库**、`LIMIT` 无 `ORDER BY` ⇒ 结果不可复现。<br>⚠️ **删除次序**：`/rag/ask` 2026-10-03（`DEC-057`）· `/rag/jwt_ask` 2026-10-04（`DEC-064`）· 余下 2 条 2026-10-04（`DEC-065`）。<br>📌 **教训（⛔ 不随删改而失效）**：`tags` 是**自述**，⛔ 别拿它当"这条是桩"的判据 —— `/rag/ask` 就是自述"模拟类"却查真库的反例 |
| 🔴🔴 **「响应体里有 `"requested_by": user_name` ⇒ 这个端点按人筛过了」** | ⛔ **那只是个【回显】** —— 它告诉调用方"你是谁"，**与 SQL 里有没有 `WHERE` 毫无关系**。<br>📌 **两条可打印的计数**（**2026-10-04** 删 `/rag/ask`（`DEC-057`）与 `/rag/jwt_ask`（`DEC-064`）后实测）：`grep -c '"requested_by"' api/api_v1_rag.py` ⇒ **10**；而 `grep -c 'WHERE requested_by' api/api_v1_rag.py` ⇒ **3** —— 🔴 **但 3 里有 2 处是【注释】**（`DEC-056` 乙段加的 · `DEC-064` 墓碑加的）⇒ **真正在 SQL 里的只有 1 处**(`:415`)。<br>⚠️ 这两组数**都会随端点增删而变**（删 `/rag/ask` 前是 **12 / 5 / 3 处**；`DEC-057` 后是 **11 / 4 / 2**）⇒ **判据要用上面那条 `\| grep -v '#'` 的写法现算**，⛔ 别照抄本文里的数字。<br>⇒ ⚠️ **所以这条判据必须写成 `grep -n 'WHERE requested_by' api/api_v1_rag.py \| grep -v '#'`** —— 本仓判据纪律第 2 条：「批量替换后按位置核，⛔ 别只数替换了几处 —— **注释里也有同样的串**」。<br>⇒ 带引号的 **10** 处**没有一处在 SQL 里过滤**（实测 0），其中 **4 处在【写入】函数里**（`:169` `:269` `:333` `:363`）—— 与读侧过滤**根本不搭界**。<br>⚠️ **2026-10-03 乙段后，8 条读端点【恰好】都是真过滤了**（⚠️ 该口径当时**含 `/rag/ask` 与 `/rag/jwt_ask`**；两条都已删 ⇒ 现在是 **6 条**，见本节开头那段后续说明）—— 但「回显」与「过滤」**对得上纯属巧合**，⛔ **不是因果关系**；那个巧合正是这条误读危险的地方（下一条新端点照抄回显就会再犯）。<br>⇒ **本仓最容易踩的误读。** 判据只有一条：**去那条端点的 SQL 里找 `WHERE requested_by`** —— ⛔ 别看响应字段（`DEC-056` §1.2） |
| 🔴 **「2026-10-03 修过隔离了 ⇒ 检索都隔离了」** | ✅ **2026-10-03（乙段）后【成立】** —— 8 条检索路径全部收口（⚠️ **现存 6 条，见本节开头**）。<br>⚠️ **但这句话在 2026-10-03 当天曾经是错的** —— 「甲段」只收口 **4 条**，`/rag/jwt_ask` 与 `/rag/stream_search` 当时**照样能读到别人的文档**（当天实测：isolation_b 的 JWT 拿回 20 篇 admin 文档；stream_search 的 prompt 里**逐字**出现别人的文档）。<br>⇒ **教训**：「修过」≠「都修好」 —— ⛔ **说这句话必须带【哪个阶段】**；判据是 `api/test_isolation.py` **覆盖到哪几条**，⛔ 不是"今天有人动过这个模块" |
| 🔴 **「`user_id` 是本文件在过滤」** | ⛔ **不是** —— **甲段那 4 条**只是**把 `user_name` 往共享层传**（`hybrid_search_api` · `rerank_search_api` · `rewrite_search_api` · `unified_search`），过滤**发生在** `db.search_similar` / `bm25_index.bm25_search`（`DEC-056` 决策 5：**共享层承重**）。<br>⇒ **要改过滤改那两个；要改"谁能调"改本文件的调用点。**<br>🔴 **2026-10-03 更正**：本行原先写「**本文件一行 SQL 都没改**」—— **乙段起不成立**：`jwt_ask` 补了 `WHERE`（**当时** `:557`；⛔ **该端点 2026-10-04 已整体删除** · `DEC-064`）· `stream_search` 的裸 SQL **被删掉**改调共享层（`:637`）。<br>⇒ 正确说法（**按 2026-10-04 现状**）：**走共享层的那 5 条不碰 SQL；自己写 SQL 的读端点只剩 `pg_search` 一条**（`DEC-056` 时是 3 条：`/rag/ask` 已删 · `DEC-057`；`/rag/jwt_ask` 已删 · `DEC-064`）—— **它改的就是本文件**。 |
| 「`/rag/stream_search` 带真中断」 | ✅ **2026-10-03 起【成立】**（`③` Task 5 · `B2`）—— 客户端断开 ⇒ 取消传给生成器 ⇒ 关上游流。⚠️ 之前写这句是**错的**（`CLAUDE.md`/`README` 都写过）。<br>⚠️ **但"真中断"≠"账单停了"** —— 本机看不到上游出账（`DEC-052` §遗留·2）。<br>🔴 **2026-10-03 更正**：这句**只在"早切"（还没吐字就断）时成立** —— 见下一行 |
| 🔴🔴 **「`finally` 里 `await stream.aclose()` 就等于"把上游关了"」** | ⛔ **不够** —— **二次投递的取消**会在下一个真实挂起点重投：`aclose()` 一挂起 ⇒ 抛 `CancelledError` ⇒ **`finally` 剩余部分整体作废**。<br>⚠️ **真服务实测（2026-10-03）**：「晚切」时计数 `2.0→2.0` ❌、**无 `[cancel]` 日志** ❌、半截 **0 条** ❌ —— 而**单测当时 13 条全绿**（假流的 `aclose()` 不抛）。<br>⚠️ **早切测不出来**：生成器**还没被推进过** ⇒ `aclose()` 不必真收尾 ⇒ **不挂起 ⇒ 打不断**。**只有「用户已经看到字再点停止」才露出来**（而那才是主场景）。<br>✅ **两条一起**（缺一不可）：① **同步**收尾（计数/日志/落盘）提到**任何 `await` 之前** · ② 关流包 `anyio.CancelScope(shield=True)`。<br>🔵 **2026-10-04 起这两条【不在本文件里】了** —— 它们搬进了共享层 `api/sse.py` 的 `sse_stream`。<br>📌 判据（可打印）：`api/test_cancel_propagation.py`；两条修法**各有一条用例独立钉住**（`…survives_interrupted_aclose` 钉 shield · `…lands_even_when_aclose_itself_fails` 钉顺序 —— 实测把关流挪回前面 ⇒ **只有后者变红**）<br>📄 `DEC-054` · 复盘 `docs/复盘/2026-10-03-单测全绿而真服务全废.md` |
| 🔴 **「`stream_search` 里有 `try/except/finally`」** | ⛔ **2026-10-04（`B1` 批 3）起没有了** —— 整段换成 `sse_response(sse_stream(...))`（`:731`），<br>骨架在 **`api/sse.py`**（`:731` 就是 `sse_response(...)` 那一行）。⚠️ **但本端点【不是】用骨架默认值** —— 它显式覆盖了三处（`ensure_ascii=True` · `on_error` **只发 error 帧** · `chunk_delay=0.01`），<br>⇒ ⛔ **别按"骨架的默认行为"去读这个端点**，也别把 `/agent/*` 四条链的形状套过来（它们三处都是默认值）。<br>🔴 **最反直觉的一条**：RAG 的帧序是 `内容 → [DONE] → sources`（`[DONE]` 在 `sources` **之前**），而骨架**一个字都不补尾巴**（`on_complete` 整段自管）。 |
| 🔴 **「自己去 `request.is_disconnected()` 轮询才知道客户端断了」** | ⛔ **不用，那是框架给的** —— uvicorn 报 `spec_version 2.3` ⇒ Starlette 已监听 `http.disconnect` 并**取消生成器**。<br>⇒ 真正的缺口只有「**停下并关掉上游**」这一件。**自己加轮询 = 多余，且会掩盖真缺口**（`DEC-052`） |
| 🔴 **「中间件日志里那个秒数 = 生成耗时」** | ⛔ **不是** —— 它记到**响应开始返回**为止。实测：`(0.019s)` 的那条客户端收了 **27KB**、`(0.004s)` 的那条 **3 秒后**才 cancel。<br>⇒ ⛔ **别拿它当"生成提前停了"的证据**（第一版就这么误读过 · `DEC-052` §真服务实测） |
| 🔴 **「换两个字问同一个问题就能测取消」** | ⛔ **会被语义缓存吃掉** —— 问句只差"基线/切断"⇒ 当成同一个问题、`0.006s` 返回全量 ⇒ **根本没在生成，取消测不出来**。<br>⇒ 测取消**必须换语义上不同的问句** |
| 🔴 **「历史里那条助手消息是完整回答」** | ⛔ **可能是半截**（`③` Task 6 · `B3` 起）—— 被中断的那轮存进去的答案**尾部带 `INTERRUPTED_SUFFIX`**（"…（本次回答被中断，以上为已生成部分）"）。<br>⇒ **读历史的人（人 / 模型 / 另一个脚本）必须看这个尾巴**，⛔ 别把半截当结论。⚠️ 这个尾巴是**故意**进 prompt 的：不标 ⇒ 模型会把断掉的话当成自己说完了（`DEC-053`）。<br>🔵 **2026-10-04（`DEC-055`）起还有机器可读的那一份**：每条都是 `{role, content, status}`，`status ∈ done / cancelled / error`。<br>⚠️ **`cancelled` 与 `error` 的中断标记串【是同一个】**（`INTERRUPTED_SUFFIX`，有意不另造）⇒ **要区分只有 `status`**；<br>🔴 **老条目（`DEC-055` 之前写的）没有 `status`** ⇒ `get_chat_history` 读的时候**补成 `done`**（按"完整答案"处理，因为那时根本不存半截） |
| 🔴 **「取消后用户那问句也没了，是设计如此」** | ⛔ **不是设计，是碰巧** —— 改动前 `append_chat_history(user, …)` 与答案写在同一段收尾代码里，取消先 `raise` ⇒ **两个一起丢**。<br>⇒ **2026-10-03（`B3`）已让取消路径成对写**（`DEC-053`）。<br>✅ **2026-10-04（`DEC-055`）**：**`except Exception` 那条也成对写了**（`status="error"`）—— 改前它**连提问一起丢**。⚠️ **三条出口现在都留痕，且都成对**；`persist_turn` 里那条「**空答案 ⇒ 一条都不写**」是唯一的"不写"分支（防空的助手消息污染下一轮 prompt） |
| 🔴 **「`/rag/upload_document` 里没看到 `invalidate_bm25_cache()` ⇒ 它不清 BM25 缓存」** | ⛔ **2026-10-04 起这是误读**（`DEC-063`）—— 不变量**下沉到了写操作自己那层**：它的插入走 `db.insert_document()`（`:321`），而**那个 helper 自己清缓存**。<br>⚠️ **改前它确实不清**（待办 **N3**）：上传的新文档在本进程的 BM25 召回里"不存在"，直到别的写路径顺手清了或重启 —— 而**同一个坑 2026-09-11 修过一次、只修给了 `/rag/insert`**。<br>⇒ **判据不是"这个函数里有没有那句话"，是"它写库的那一层有没有"** —— 守卫 `api/test_bm25_cache_invalidation_wiring.py` 正是**从 AST 推导写路径**来判这件事的。 |
| 「`/rag/search` 是纯检索」 | 🟡 **它能生成答案** —— 传 `generate_answer: true` 即可（**默认 `False`**，`api/schemas.py:14`） |
| 「检索都走 `rag_pipeline`」 | 🔴 **`/rag/stream_search` 不走 pipeline** —— 它直接调**共享层**的**纯向量那一档**<br>`search_similar(query_embedding, req.top_k, user_id=user_name)`，**不经过** `pipeline` / `hybrid_search` / **BM25** / **reranker** ⇒ **与 `/rag/search` 召回不同源**。<br>⚠️ **2026-10-03 更正**：本行原先写「**内联裸 SQL**」—— 乙段起**不再成立**（改走共享层了）。<br>🔴 **别把这句和隔离混起来**：乙段让它的**过滤**跟上了（共享层带 `WHERE`），但**召回源【没】拉齐** —— 这两件事在这条端点上恰好相反：**隔离对齐了，召回没对齐** |
| 🔴 **「本文件的端点都接了会话上限」** | ⛔ **不是** —— **2026-10-05（`DEC-073`）起 4 条**：`/rag/stream_search` · `/ws/agent`（B8 · 2026-10-01）+ **`/rag/search` · `/rag/rewrite_search`**（B8 **且** B11 · 2026-10-05）。<br>⚠️ **新增的两条是"改前完全没有闸"** —— 它们跑的却是**每次都花 LLM 钱**的改写/生成链（`DEC-073` §一）。<br>**原先**这里要解释「`/rag/async_ask` · `/rag/parallel_ask` **故意不接**（它们不调 LLM）」—— 🔴 **2026-10-04（`DEC-065`）这两条端点已删，那句话不需要了**。<br>⚠️ **计数沿革**：4 条 →（2026-10-03）3 条 [`/rag/ask` 删 · `DEC-057`] →（2026-10-04）2 条 [`/rag/jwt_ask` 删 · `DEC-064`] →（2026-10-04）**0 条** [余下 2 条删 · `DEC-065`] →（2026-10-05）**4 条** [`DEC-073` 新增 2 条]。<br>🔴 **反向守卫随之删除**：`api/test_session_budget_wiring.py` 与 `api/test_breaker_wiring.py` 各有一张"**不许接**"的豁免清单，**清单删空后 `for` 体一次都不跑 = 恒绿假通过** ⇒ 两段守卫**已删除**，保护**收敛到** `api/test_removed_endpoints.py`（判据 = **404**）。⚠️ **代价**：将来再加"不花钱"的端点，**没有测试会自动拉红**（详见两文件的模块注释与 `DEC-065`）。<br>⇒ ⚠️ **新增的守卫刻意用"点名"而不是"扫描"**：`api/test_rag_billing_wiring.py::test_rag_endpoints_gate_both_session_and_global` **参数化点名** `unified_search` / `rewrite_search_api` 两个函数，⛔ **不是"扫一遍找没接闸的"**。<br>⛔ **两者的区别是致命的**：扫描式守卫要先"认出哪些端点该接闸"——**认不出的它一律放过**，于是漏掉的恰恰不被报（`DEC-066` 的形状盲区）。<br>⚠️ **代价**：点名式**不会**自动发现"将来新增的端点有没有接闸" ⇒ 那要靠**改本文件时人回头看这一行**（已在此写明）。 |
| ⚠️ **「`/rag/stream_search` 一直有 `thread_id`」** | 🔴 **2026-10-01 才补的**（B8，query 参数）。`QuestionRequest` **没有**这个字段 ⇒ 它**不在 body 里** |
| 🔴 **「`/ws/agent` 的额度是按人算的」** | ⛔ **按连接算** —— 会话 id 仍是**每连接生成的 uuid**（`thread_id = f"ws-{uuid4}"`）⇒ **断开重连 = 换一个新桶**。<br>✅ **2026-10-05（`DEC-075`）：不再记成 `"unknown"` 了** —— 整条链现在要过**首帧认证**（`deps.require_ws_user`），`user_name` 是**认证出来的真人**，账也记在他头上。<br>⚠️ **但"按连接算"没变**：WS 没有客户端传上来的会话 id ⇒ 重连换桶。**这是有意留下的口子**（`DEC-075` 遗留·2）——全局日级熔断 B11 仍罩着，不会因此失控。<br>🔴 **判据怎么来的**（别信这句话，去跑）：`venv/bin/python scripts/check_route_auth.py` ⇒ 无鉴权路由**只剩 `/api/v1/` 一条**。<br>⚠️ **`MIDDLEWARE_EXEMPT_PATHS` 与这条无关**：那两个中间件是 `BaseHTTPMiddleware`，**只看 `scope["type"]=="http"`** ⇒ **永远看不到 WebSocket**；WS 的鉴权只能挂在**路由自己的依赖**上。 |
| 🔴🔴 **「乙段之后，单测 patch `api_v1_rag.get_db` 就够短路了」** | ⛔ **不够，而且本机看不出来** —— 乙段让 `stream_search` **改调共享层** `db.search_similar` ⇒ **`get_db()` 的解析位置从 `api_v1_rag` 的模块全局搬到了 `db.py` 的模块全局**。<br>⇒ 只 patch `rag_mod.get_db` 的测试**够不着真实连接点**，会**真去连库**。<br>🔴 **本机为什么看不见**：本机 Postgres 真开着 ⇒ 连上、`fetchall()` 回 `[]` —— **与假连接的返回值恰好一样** ⇒ **全绿**。**CI 没有 Postgres ⇒ `Connection refused`**（实测 12 条红，`2026-10-03`）。<br>⇒ **判据**：`grep -rn 'setattr(.*get_db' api/test_*.py` —— 逐条看它 patch 的是**哪个模块的** `get_db`；<br>⚠️ **改了任何函数的【依赖来源】（换模块调 / 走共享层 / 抽公共层）⇒ 必须回头过一遍这个 grep**。<br>📄 `docs/复盘/2026-10-03-CI同款命令不等于CI等价物.md`（**教训是"入口没指向 `scripts/ci-local.sh`"**） |
| 🔴🔴 **「本文件的 tools 跟别处一样，`calculator` 早就收口过了」** | ⛔ **改前不成立**（`DEC-066`）—— `get_agent_executor()` 里**本地又手抄了一套 tools**（**第 6 份拷贝**），其中 `calculator` **一直写的是 `eval`**（`2c1a922` · 2026-07-17 起），<br>而 `/ws/agent` **整条没有鉴权** ⇒ **匿名可达的任意代码执行**。⚠️ **两道 AST 守卫都看不见它** —— 旧判据只认「`ast.Call` 的 `func` 是裸名 `eval`」，而本行是 `asyncio.to_thread(eval, expression)`（`eval` 是**实参**）。<br>✅ **2026-10-04 已收口**（换 `safe_math.calculate`）+ **守卫判据改成只认名字**（与调用形状无关）。<br>⚠️ **同批改了 `search`**：`DuckDuckGoSearchRun` → `search_tools.web_search`（`duckduckgo.com` 本机不通 · `DEC-051`）。<br>✅ **2026-10-05（`DEC-075`）：鉴权补上了** —— 整条链要过首帧认证（`require_ws_user`），**匿名已连不进来**。<br>🔴 **⛔ 别读成"这处 `calculator` 以后安全了"**：`expression` 仍是 **LLM 生成**的，而 LLM 的上下文含**用户提问 / 搜索结果** ⇒ **间接提示注入面依旧存在**。<br>⚠️ **攻击者换人了而已**：改前是路人，现在是**持合法凭据的用户**。⇒ 三道闸（`safe_math`）**一条都不能撤**。 |

## 关联

`docs/decisions/DEC-056-多用户资源隔离的现状审计与分阶段收口.md` ·
**`docs/decisions/DEC-057-删除-rag-ask.md`** · **`docs/decisions/DEC-064-删除-rag-jwt-ask.md`** ·
**`docs/decisions/DEC-065-删除-无鉴权端点与收口鉴权.md`**（本文件删过的**四条**端点 —— 后两条是 `DEC-065`）·
**`docs/decisions/DEC-066-第六份calculator的eval与守卫形状盲区.md`**（🔴 **本文件 `get_agent_executor()` 的 tools 收口** —— 那处 `eval` 的第 6 份拷贝）·
**`docs/specs/safe_math.md`**（收口清单 **5 → 6 处**）·
**`docs/specs/sse.md`**（本文件流式端点的**骨架** —— 2026-10-04 起它才在本文件里）·
`后端补齐清单` **B1/B2/B3** · `docs/decisions/DEC-052-取消传播的观测对象与上游改异步.md` ·
`docs/decisions/DEC-053-中断后的半截答案存进历史并打标记.md` ·
`docs/decisions/DEC-054-取消路径的收尾顺序与关流护盾.md` ·
`docs/decisions/DEC-055-中断与异常路径的留痕口径.md`（✅ **2026-10-04 已实施** ——
`/rag/stream_search` 是它的 RAG 那一半；另 5 条 Agent 链见 `docs/specs/api_v1_agent.md`）·
`docs/契约/接口契约.md` §四 · `docs/原理/架构.md` §3.2 ·
**`docs/decisions/DEC-073-RAG侧关闭零记账的LLM通路.md`**（🔴 **本文件 `/rag/search` 与 `/rag/rewrite_search` 的闸 + 记账** ——
改前这两条链**零闸零记账**）· `docs/specs/query_rewriter.md` ·
`docs/复盘/2026-09-29-结果为空就断言能力不存在.md`
