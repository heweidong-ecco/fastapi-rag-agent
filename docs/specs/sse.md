# `api/sse.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟢 **新建并已接上全部 6 条流式端点（2026-10-04 · `③` Task 4 · `B1` 剩余 4 条链）** —— 本仓**所有流式端点的骨架**<br>⚠️ **它收的不是"重复代码"，是 5 条实测出来的顺序约束**（`DEC-054` / `DEC-052` / `DEC-050`）<br>✅ 批 2 建层 + 单测 · 批 3 两条旧端点改用它（**逐帧等价**）· 批 5 的 4 条新链**一开始就建在它上面** |
| **对外提供** | `SSE_HEADERS` · `DONE_FRAME` · `sse_frame(payload, *, ensure_ascii)` · `sse_response(source)`<br>· `graph_message_text(item, *, nodes)`（LangGraph `messages` 模式）· `llm_chunk_text(chunk)`（裸 LLM）<br>· `sse_stream(open_upstream, *, endpoint, extract, on_complete, on_cancel, on_error, ensure_ascii, chunk_delay)` |
| **谁在用** | **6 条，全部**（`grep -rn "sse_stream(" api/api_v1_*.py`）：<br>`api_v1_agent.py` —— `langgraph_chat_stream` · `advanced_agent_chat_stream` · `memory_chat_stream` · `mcp_agent_chat_stream` · `agent_plan_execute_stream`（**5 条**）<br>`api_v1_rag.py` —— `stream_search`（**1 条**） |
| **用例** | `api/test_sse_layer.py`（**15 条**，⛔ 不碰端点 —— 端点的等价性由既有两份用例"全绿且不改"来证）<br>+ `api/test_agent_stream_chains.py`（**39 条**）用**同一个骨架**驱动 4 条新链 |

## ✅ 做了什么

- **一副骨架顶掉 2（很快 6）份内联生成器** —— 删掉的将是 `api_v1_agent.py:227-310` 与
  `api_v1_rag.py:715-792` 里**逐字重复**的 `try / except / except / finally`。
- **5 条约束的落点**（模块 docstring 有表）：

  | # | 约束 |
  |---|---|
  | ① | 同步收尾（计数 → 日志 → `on_cancel`）**排在【任何 `await` 之前**」 |
  | ② | 关上游包 `anyio.CancelScope(shield=True)` |
  | ③ | `except asyncio.CancelledError: raise`（⛔ 不吞 · ⛔ 不 yield） |
  | ④ | `X-Accel-Buffering: no`（在 `SSE_HEADERS` 里，⛔ 不可省） |
  | ⑤ | 汇总**只从图的最终状态取** —— 骨架**不实现**它，而是**不提供**任何"攒块"的接口（`on_complete` 拿到的是已发文本，要状态就自己去 `aget_state`） |

- **两种 extractor**：图（按节点白名单 + 跳空 `content`）· 裸 LLM 块。`extract=None` ⇒ 原样当文本。

## 🟡 做到哪 / 缺什么

| 批 | 事 | 状态 |
|---|---|---|
| 2 | 建 `api/sse.py` + 本 spec + `api/test_sse_layer.py` | ✅ |
| 3 | 两条既有点端改用它（**行为逐帧等价**） | ✅ `api/test_agent_sse.py` + `api/test_cancel_propagation.py` **44 passed 且两份文件 diff 为空** |
| 4 | 改节点（A/B/C 三张图） | ✅ 见 `agent_graph.md` · `agent_checkpointer.md` · `agent_graph_advanced.md` · `agent_graph_advanced_learning.md` |
| 5 | 4 条新 SSE 路由 | ✅ `advanced_chat` · `memory_chat` · `mcp_chat` · `plan_execute` |
| 6 | `api/test_agent_stream_chains.py` | ✅ **39 条** |

- ✅ **链 D（`plan_execute`）的「线程 → 事件循环」桥接器按计划落在调用方** ——
  `api_v1_agent.py::_ThreadTokenBridge`（`plan_task` 是同步函数、跑在 `asyncio.to_thread` 里）。
  ⛔ **共享层不引入 `threading` 依赖**；桥接器是一个「有 `__aiter__` / `__anext__` / `aclose`」的对象，
  仍走 `open_upstream`。⚠️ 它 `aclose()` **非阻塞 + 协作式**（置取消标志 + 排空队列 + 取消后台任务），
  ⛔ **不 `await thread.join()`** —— 线程杀不掉，**只能让它把剩下的跑完**（只是不再发）。
- ⚠️ **`extract=None` 是给链 D 的**：桥吐出来的**就是文本**（不是图的消息块）⇒ 原样发。
  ⛔ 别给它套 `graph_message_text`（那要 `(chunk, meta)`，会 `ValueError`）。

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| ⚠️ **① `ensure_ascii` 是个可以随便调的旋钮** | ⛔ **它是为"不改线上字节"而存在的**：`/agent/*` 一直用 `False`（中文原样），<br>`/rag/stream_search` 一直用默认 `True`（中文 `\uXXXX`）。**两处今天就不逐字相同。**<br>⇒ 抽公共层**不是顺手统一编码的理由** ⇒ RAG 显式传 `True`，把旧字节留住。<br>⚠️ 两种编码 **JSON 解码后的值相同** ⇒ 功能上无感，但**统一会让"逐帧等价"从"字面为真"变成"差不多"**。<br>📌 **已登记待裁**：要不要统一（以及为什么这条值得单裁）。 |
| 🔴 **② 骨架会自动补 `[DONE]`** | ⛔ **不会** —— `[DONE]` 与其它收尾帧的**先后是每条链自己的契约**。<br>RAG 是 `内容 → [DONE] → sources`（`[DONE]` 在 sources **之前**，很反直觉但是现状，前端已按此适配）。<br>⇒ 整条尾巴交给 `on_complete`，**骨架一个字都不补**。 |
| ⚠️ **③ 收尾期被取消要算取消** | ⛔ **不算**：`outcome = "done"` 是在**收尾之前**置的（与两条旧实现一致）。<br>⇒ `aget_state` / 落历史 / 发 sources 期间客户端断开 ⇒ **不计入 `stream_cancelled_total`**。<br>🔴 **别"顺手修正"** —— 那会改动一条**没有任何用例覆盖**的边界。 |
| ⚠️ **④ 错误路径统一成 `error + [DONE]`** | ⛔ **不是** —— 默认是那样（= `/agent/*` 现状），但 **RAG 显式传 `on_error` 只发 error 帧**。<br>理由不是保守：**`[DONE]` 会被读成"正常收尾"**，RAG 今天靠"**没有** `[DONE]`"分辨出错。<br>⚠️ 统一会把"出错"变得像"正常结束"。 |
| ⚠️ **⑤ 取消时先关流、再收尾** | ⛔ **反了**（约束①）：**三件同步的收尾在前，`aclose()` 在最后**。<br>`await` 会被**二次投递的取消**打断 ⇒ 关流放前面，后面那三件**一件都不跑**，而**单测全绿**（`DEC-054`）。 |
| ⚠️ **⑥ `extract` 收到的是 `(chunk, meta)`** | **看链**：无子图（B/C）= `(chunk, meta)`；**有子图（advanced_chat）必须 `subgraphs=True`**，形状变成 `(namespace, (chunk, meta))` —— **不开它，一个字都流不出来**。<br>⚠️ 归一化在 `graph_message_text` 里，⛔ 端点别再解一次。<br>🔴 且**先看 `len(item) == 3`**：`ns` 自己就是 tuple，`isinstance(item[0], tuple)` **分不出** `(ns, chunk, meta)` 与 `(ns, (chunk, meta))` —— 顺序写反 ⇒ ValueError。 |
| ⚠️ **⑦ 这块是不是 token 有办法判** | ⛔ **没有**。而且**不止 LLM 会产块**：实测 `advanced_chat` 的 `supervisor`（它 `return state`）会把它收到的<br>**用户提问原文**当"新消息"发出来 ⇒ 不加白名单，**用户会先看到自己的问题被回显一遍**。<br>⇒ **就按节点名收**（`nodes=` 白名单）。 |
| 🔴 **⑧ 这里是记账的地方** | ⛔ **不是** —— 本模块只**发帧**，**一行 token 记账都没有**。<br>⚠️ 但要记住一件**极易踩的反向坑**：节点内部把流**聚合成一条消息**去记账时，<br>**必须对【所有】块做 `+`，⛔ 不许跳过 `content` 为空的块** ——<br>实测本仓 provider 把 `usage_metadata` 挂在**最后一块**（`content=''`）上，跳过它**账就没了**，<br>而接口一切正常。判据 ⇒ `fastapi-rag-agent-TODO待办/探针-流式与记账.py`。 |
| ⚠️ **⑨ `SSE_HEADERS` 可以直接传** | ⛔ **不能** —— `StreamingResponse` 会**持有并改写**自己的 `headers` ⇒ 共享同一个 dict 会让所有响应**串台**。<br>⇒ `sse_response()` 每次都 `dict(SSE_HEADERS)` 复制一份（用例：`test_response_headers_are_copied_not_shared`）。 |

## 关联

| 文档 | 说明 |
|---|---|
| `docs/specs/api_v1_agent.md` · `docs/specs/api_v1_rag.md` | 批 3 要改用本层的两条端点（含它们**不能动**的契约：帧序、限速） |
| `DEC-054` | 约束①（同步收尾排在 `await` 前）· 约束②（shield）—— **真服务实测** |
| `DEC-052` | 约束③（取消时 ⛔ 不 yield `[DONE]`）· `stream_cancelled_total` |
| `DEC-050` | 约束⑤（汇总只从图状态取，⛔ 不是攒块）—— **真服务撞出来的** |
| `docs/specs/metrics.md` | `track_stream_cancel` / `stream_cancelled_total` 的本尊 |
| `fastapi-rag-agent-TODO待办/探针-真流式与子图.py` | ⚠️ ⑥ 那张六剧本表（`subgraphs` 开关与产出形状） |
| `fastapi-rag-agent-TODO待办/探针-流式与记账.py` | ⚠️ ⑧ `usage_metadata` 挂在哪一块上 |
