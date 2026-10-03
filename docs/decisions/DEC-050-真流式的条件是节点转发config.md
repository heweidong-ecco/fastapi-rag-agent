# 决策记录：DEC-050 · **真流式的条件是「节点转发 `config`」** —— 而不是"加一条 SSE 路由"

- 日期：2026-10-03（**发现 + 裁定 + 落地同日**）
- 状态：**已采纳** —— 落点是 `③` Task 4（`B1`）
- 关联：`docs/specs/agent_graph.md`（**另一半改动在这里**）·
  `docs/specs/api_v1_agent.md`（路由 + 实施计划 ③）·
  `api/test_agent_sse.py`（**判据的本体**，12 例 · 纯离线）·
  `DEC-048`（B4 审批 —— 本条的 `tool_calls` 聚合直接决定它灵不灵）

## 决策事项

**`/agent/langgraph_chat` 的真流式怎么做。** 业务方 2026-10-03 在两个选项上裁定：

| 问题 | 选项 | 选了 |
|---|---|---|
| 怎么让 agent 的流式"**真的是流式**"？ | **甲** · 只改节点取流方式 / 乙 · 把节点改成 `async` / 丙 · 另起一个"流式专用图" | **甲** |
| 这个选择要不要落一份决策档？ | 落 / 不落 | **落 `DEC-050`** |

## 为什么这个决定**必须**单独立档（🔴 计划里没有这一句）

`docs/specs/api_v1_agent.md` 的实施计划 ③ 把 Task 4 写成
「**服务端加一条 SSE 路由**」，并给了一条判据：
`assert "text/event-stream" in resp.headers["content-type"]` + `assert resp.text.count("data:") >= 2`。

### 🔴 那条判据**抓不到假流式**

**后端一次性拿到整段、再原样吐出来**，也是 **1 条 `data:`**；加个 `[DONE]` 就是 **2 条** ⇒ **照样绿**。
即：

| 写法 | 接口长相 | 那条弱判据 | 实际 |
|---|---|---|---|
| 不接 `config` + `invoke()` | `text/event-stream` + `data:` 帧 | ✅ 过 | **1 块**（整段，`on_llm_end` 吐的）＝**假流式** |
| 接 `config` + `.stream(config)` | **完全一样** | ✅ 过 | **N 块**、时间戳递增 ＝真流式 |

⇒ **"有没有这条路由" 和 "它真的是不是流式" 是两件事**，而计划里只写了前者。
真流式的**必要条件在图的一侧，不在路由这一侧**。

### 实测证据（假模型探针⑦/⑧，**不联网、不花钱**）

`astream(stream_mode="messages")` 的块从哪来 —— 读 `langgraph/pregel/_messages.py` 得到三个来源：
① `on_llm_new_token`（真·token）② `on_llm_end`（整段）③ `on_chain_end`（节点返回值）。
**实测四个剧本**：② 被 `dedupe=True` 拦掉、③ **根本不会发** ⇒ **每 token 恰好一块、不重复**。

⚠️ **而这个性质【没有】写在源码契约里** —— 它是实测出来的。
⇒ 已**钉成用例**（`test_stream_route_emits_one_frame_per_token`）：
哪天 langgraph 升级后开始发 ③，这条会**红**，而不是**悄悄把答案吐两遍**。

## 备选方案

### 甲 · 只改节点取流方式（**采纳**）

`agent_decide` 保持**同步**，只加一个参数、把回调转发下去：

```python
def agent_decide(state: AgentState, config: RunnableConfig):
    response = None
    for chunk in llm_with_tools.stream(state["messages"], config=config):
        response = chunk if response is None else response + chunk
    return {"messages": [response]}
```

| 好处 | 代价 |
|---|---|
| **改动面最小** —— 图的结构、路由、3 个共用此图的模块**全不动** | ⚠️ **换了一种取流方式**（`invoke` → `.stream`）⇒ **要证明没弄坏别的**。<br>✅ 已守：`test_non_streaming_invoke_still_works`（同步 `invoke()` 仍然通） |
| 同步 `invoke()` **不受影响** | ⚠️ 聚合必须用 `AIMessageChunk.__add__`，⛔ **不能 `content +=`**（见下） |
| 一条改动**同时**让 `/agent/langgraph_chat` 和新的流式路由都对 | |

### 乙 · 把 `agent_decide` 改成 `async def`（**⛔ 明确否掉**）

**看着更"对"**（异步服务 + 异步节点），**实测会直接弄坏非流式路径**：

```
TypeError: No synchronous function provided to "agent"
```

`/agent/langgraph_chat` · `api_v1.py` · `api_v1_rag.py` **都在用同步的 `graph.invoke()`** ——
异步节点会让它们**当场抛错**。⇒ **否掉**。

✅ **而且它没必要**：**同步节点 + 同步 `.stream(msgs, config=config)` 就能真流式**
（探针实测 6 块、时间戳递增）。**这个是本次最反直觉的一条实测结论** —— 已进
`docs/specs/agent_graph.md` 的「⚠️ 看代码会误判」表。

### 丙 · 另起一个"流式专用图"（**否掉**）

| 好处 | 代价 |
|---|---|
| 不碰现有图，风险隔离 | 🔴 **一份图变两份** ⇒ `B4` 审批 / `B5` 队列 / `B6` 续跑**全要跟着复制一遍** —— 本仓刚刚才因为「**同一份代码复制了 5 次**」立了 `DEC-049` |
| | 两份图**会漂**：改了一边忘了另一边 ⇒ 流式与非流式的**审批行为不一致**，而**没有任何测试会发现** |

⇒ **否掉**：本仓的拷贝文化是**已经证明过会出事**的（`DEC-049` 的 5 处 `eval`）。

### 丁 · 不加参数，改在路由侧"自己攒"（**否掉 —— 但值得写下来**）

原本的设想：路由拿 `astream` 的块**自己攒**出 `summary`。**这是本次真服务跑出来的 bug**（见下）。

## 落地形状（甲）

**两处改动，缺一不可**：

| 文件 | 改什么 |
|---|---|
| **`api/agent_graph.py`** | `agent_decide` 加 `config: RunnableConfig` + `.stream(…, config=config)` + `+` 聚合。**189 → 222 行**（多出的全是"为什么必须这样写"的注释） |
| **`api/api_v1_agent.py`** | 新增 `POST /agent/langgraph_chat/stream`：`StreamingResponse` + `media_type="text/event-stream"` + **`X-Accel-Buffering: no`** |

### ⚠️ 细节一：`X-Accel-Buffering: no` 不是可选项

少了它，**Nginx / Cloudflare 会把整段缓冲住** ⇒ **后端真流式，到了用户那儿又变回假流式**。
本仓的目标是**上 Cloudflare 隧道**（`DEC-033` 🟡C）⇒ **这条现在就得上**。

### ⚠️ 细节二：聚合必须用 `+`，⛔ 不能 `content +=`

`tool_calls` 是**碎片化**到达的（name 一块、args 几块）。
只拼 `content` 会**把 `tool_calls` 丢掉** ⇒ `should_continue` 判不出 `"approval"`
⇒ 🔴 **`B4` 人工审批静默失效**，**而接口返回 `{"status":"answered"}` 一切正常**。
✅ 守卫：`test_agent_decide_preserves_tool_calls`。

## 🔴🔴 真服务跑出来的 bug（**计划里完全没写的一步**）

Task 4 的 Step 4 是「**用真服务验证**，⛔ 别只用 `TestClient`」。**它真的抓到了东西。**

**第一步（文本类问题）**：29 个 token 帧，时间戳严格递增 `0.640s → 0.821s`，`status: answered` + `[DONE]`。✅

**第二步（搜索类问题）**：返回 `status: "pending_approval"`，而**图其实已经跑完**。

- **症状**：`tool_calls` 的 name 被拼接成 **`"date_todayduckduckgo_search"`**。
- **排查**：先怀疑"并行工具调用的合并把索引 0/1 粘一起了" ⇒ **用探针证伪**（`+` 合并能保持索引分开、名字正确）。
- **真因**：**是我引入的** —— 结尾的 `summary` 是**把流过 `agent` 节点的块攒起来**算的，
  而模型因工具返回"未找到工具"**重试搜索** ⇒ `agent` 节点进了**多次** ⇒ 攒出来的东西带着**上一轮的** `tool_calls`
  ⇒ `summarize_agent_result` 误报 `pending_approval`。
  🔴 **后果很重**：前端会**永远等一个不会来的审批**（而图早就结束了）。
- **修法**：**从图的最终状态取**，⛔ 不是从块攒：

```python
state = await agent_graph.aget_state({"configurable": {"thread_id": thread_id}})
summary = summarize_agent_result(state.values or {})
```

  这**与 `/agent/langgraph_chat` 完全同一套语义**。
- **再验**：**216 个内容帧** + `status: answered` + `pending_tool_calls: null` ✅
- **先 RED 后 GREEN**：`test_status_comes_from_final_state_not_from_streamed_chunks`
  （`_TwoRoundModel` 逼出第二轮 + `_SpyGraph` 记下 `aget_state` 被调用）

> 📌 **这一条是本 DEC 想留下的最大的东西**：
> **"把流过的块攒起来"是个看起来自然、实际会错的写法** —— 而它错得**不报错、接口照常返回**。
> ⇒ 已进 `docs/specs/api_v1_agent.md` 的「⚠️ 看代码会误判」**表首行**。

## ⚠️ 顺带照出来的两个既有 bug（**不是 `③` 引入的**）

真服务跑的价值不止验证 —— 它把**从来没被端到端跑过**的两条路径照了出来：

1. 🔴 **`SENSITIVE_TOOLS` 的默认值匹配不到任何真实工具 ⇒ 审批其实永不触发**。
   真实工具名 = `['calculator', 'date_today', 'duckduckgo_search']`，默认白名单写的是 **`search_tool`**（那是**变量名**）⇒ **交集为空**。
   ⚠️ `validate_approval_config()` **只查"非空"，不查"名字真的存在"** ⇒ **启动自检过得去，功能却从未生效**。
   ⇒ 正是硬门 D 说的「**验收时才发现接管从来没发生过**」。
2. 🔴 **`tool_execute` 的分派名字也对不上** —— 判 `if tool_name == "search"`，真名是 `duckduckgo_search` ⇒
   永远返回字面量 `"未找到工具: duckduckgo_search"`。
   ⚠️ **后果模型侧可见**：模型会**反复重试搜索** ⇒ **这正是上面那个多轮聚合缺陷的触发器**。

📌 **两条都记进了 `docs/specs/agent_graph.md` 的 🟡 节**，⛔ 本条 DEC **不处理**它们。

> ✅ **2026-10-03 已结** —— 上面两条**当天就单独立了 `DEC-051`**（业务方裁：**两处都修 · 名字不存在就不许启动 · 一并换成 Bing 版 `web_search`**）。
> · ① 默认值改成真工具名 `web_search` + `validate_approval_config()` **加第二段硬拦**（名字不存在 ⇒ 拒绝启动）
> · ② 两个文件的 `tool_execute` 都改成**查 `TOOLS_BY_NAME` 表**（`agent_checkpointer.py` 是**第二处现场**，活路径 `/agent/memory_chat`）
> 📄 `DEC-051-工具名分派与审批白名单的标识符勘误.md` · 📌 守卫 ⇒ `api/test_tool_dispatch.py`（9 例）
> ⚠️ **但上面那个"多轮聚合缺陷"本身没消失** —— 它守的是**端点该从哪取状态**，与"模型为什么重试"是两件事。
> ⇒ `api/test_agent_sse.py::test_status_comes_from_final_state_not_from_streamed_chunks` **仍然必须留着**。

## 反悔成本

| 若将来要改成… | 要动哪里 | 成本 |
|---|---|---|
| **撤掉流式**（认为不值得） | 删路由 + 删测试 + `agent_decide` 改回 `invoke` | **低**（改动面本来就小 —— 这正是选甲的理由） |
| **改成 `async` 节点**（乙） | 要**同时**改掉 3 个模块的同步 `graph.invoke()` 调用点 | **高**，且 🔴 **需要先证明没有第 4 个调用点** |
| **换 langgraph 版本导致块重复** | 不必改代码 —— `test_stream_route_emits_one_frame_per_token` **会先红** | **低**（判据已钉住，不是"上线才发现答案吐两遍"） |
| **加更多流式路由** | 照抄本路由的形状（⚠️ `X-Accel-Buffering` 与两条前置闸**要跟着**） | **低** |

## ⚠️ 遗留（**本 DEC 不处理，但必须留痕**）

1. ⚠️ **只有 1 条路由是流式的**（`/agent/langgraph_chat/stream`）—— 其余 **29 条仍全非流式**。
   硬门 A 要的是"**该流的流**"，⛔ **不是"流了一条就算完"**。
2. ⚠️ **"每 token 恰好一块"是实测性质，不是源码契约** —— 已钉用例，但它是**经验性**的。
3. ⚠️ **`B2`（cancel 传播到上游）· `B3`（半截答案怎么处理）仍未做** —— 见实施计划 ③ 的 Task 5 / 6。
   🔴 **B2 自标「最容易假完成」**，而**本条的流式路由同样没有 cancel 处理**（客户端断开后图会继续跑完）。
4. ⚠️ **`docs/specs/api_v1_agent.md` 实施计划 ③ 里那条弱判据（`data:` ≥ 2）没被删**，
   只在 Task 4 里**标了"不够"**并指向 `api/test_agent_sse.py` —— 因为 Task 5/6 还要照那个格式写。
