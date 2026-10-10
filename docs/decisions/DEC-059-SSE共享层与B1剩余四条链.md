# 决策记录：DEC-059 · **`api/sse.py` 共享层 + `B1` 剩余 4 条链**

- 日期：2026-10-04
- 状态：**已立 · ✅ 已实施**（4 条新路由 · 2 条旧端点改走共享层 · 逐帧等价）
- 分支 / PR：`feat/b1-stream-remaining-chains` —— **一个完整任务一个 PR**
- 触发：`ROADMAP.md` `③` Task 4（2026-10-03 · `DEC-050`）只开了**第一条**流式路由
  （`/agent/langgraph_chat/stream`）⇒ **硬门 A「该流的流」的缺口没关掉**。
  业务方 2026-10-04 就本条裁了三件事（见 §一）。
- 计划全文：**仓外 · 机器本地、未入库** —— 本机 `~/.claude/plans/` 下那份会话计划（`B1 剩余 4 条链 · Agent 端真流式 + api/sse.py 共享层`）
- 规划时的**改动面普查**：`fastapi-rag-agent-TODO待办/硬门A-Agent端流式勘察-20261003.md`

---

## 一 · 业务方 2026-10-04 的三条裁定（本条的**前提**，⛔ 不是实施者的选择）

| # | 事项 | 裁定 | 本文档在哪落地 |
|---|---|---|---|
| **1** | **落地形状** | **抽共享模块 `api/sse.py`，现有两条流式端点一起改**（⛔ 不是复制第 5、6 份内联生成器） | §二 · §三 |
| **2** | **`/agent/approve` 加不加流式** | **不做** —— 它是「**续跑一个已经停下的图**」，不是「生成答案」 | §五·不做什么 |
| **3** | **`plan_execute` 这一轮做不做** | **一起做**，且**只流「规划段」** | §四 |

⚠️ 同日另裁：**D 链照原样流 JSON**（三个选项里选「甲」，理由是**它是真流式** —— 硬门 A 要的正是这个）。
⇒ 它的**两条推论**写进 §四。

---

## 二 · 为什么是「共享层」而不是「再抄一遍」

在本次之前，**同一副骨架在本仓被内联抄了 2 遍**：`api_v1_agent.py::langgraph_chat_stream`
与 `api_v1_rag.py::stream_search`。而**第 3、4、5、6 遍就要开始抄了**（本轮 4 条链）。

🔴 **关键不在"重复"，在那 5 条约束"一定会被抄错"** —— 它们**全是实测撞出来的**，
而且**写错的形态是"接口一切正常"**（不会报错、不会红、单测全绿）：

| # | 约束 | 出处 | 抄错的后果 |
|---|---|---|---|
| ① | **同步收尾（计数 → 日志 → `on_cancel`）必须排在【任何 `await` 之前】** | `DEC-054` | **晚切**（用户已看到字再点停止 = 主场景）时**收尾一件都不跑**；⚠️ **单测当时 13 条全绿**（假流的 `aclose()` 不抛） |
| ② | **关上游必须包 `anyio.CancelScope(shield=True)`** | `DEC-054` | 取消作用域在**每个 await 点反复投递** ⇒ "关"这个动作**每次半途而废** |
| ③ | `except asyncio.CancelledError: raise`（⛔ 不吞 · ⛔ 不在里面 `yield`） | `DEC-052` / `DEC-054` | 旧实现在取消时**还发了一帧 `[DONE]`，实测真发得出去** ⇒ 接收方分不出"已取消"与"正常收尾" |
| ④ | **`X-Accel-Buffering: no` 不可省** | 反代行为 | 本地直连一切正常，**上线后变假流式**（Nginx / Cloudflare 把 SSE 攒着发） |
| ⑤ | **汇总/状态只从图的最终状态取**（`aget_state`） | `DEC-050` **真服务** | 「把流过的块攒起来」会把**上一轮**的 `tool_calls` 混进来 ⇒ 判成 `pending_approval`，而图**早就跑完了** ⇒ **前端永远等一个不会来的批准** |

> ⭐ **一句话**：这 5 条**不是"代码风格"**，是**踩过的坑的形状**。
> 「抄 2 遍」已经到极限了 —— 第 3 遍开始，**抄错的概率**比**抽层的成本**高。

---

## 三 · 共享层的边界：**进了什么 · ⛔ 什么没进**

### 3.1 进了（`api/sse.py`，274 行；spec ⇒ `docs/specs/sse.md`）

| 成员 | 职责 |
|---|---|
| `sse_stream(...)` | **骨架本体** —— 打开上游 → 逐块发帧 → 收尾；**5 条约束都在它里面** |
| `sse_frame(payload, *, ensure_ascii=False)` | 一帧 `data: {json}\n\n` |
| `sse_response(source)` | 包成 `text/event-stream`（三个头；⚠️ **每次 copy 一份**，见 3.3） |
| `graph_message_text(item, *, nodes=…)` | LangGraph `stream_mode="messages"` 的一块 ⇒ 文本（`None` = 不发） |
| `llm_chunk_text(chunk)` | **裸 LLM**（不是图）的一块 ⇒ 文本；给链 D 用 |
| `DONE_FRAME` / `SSE_HEADERS` | 常量 |

⚠️ **骨架【不自动补 `[DONE]`】** —— 整条收尾尾巴交给 `on_complete`。
理由：**`[DONE]` 与其它收尾帧的先后是【每条链自己的契约】**，
而 RAG 那条是 **`内容 → [DONE] → sources`**（很反直觉，但**是现状**）。
⛔ **抽公共层不是顺手改行为的理由**（`DEC-050` 同理）。

### 3.2 ⛔ 没进 —— 以及**为什么不能进**（两类，理由不同）

**第一类：进去会让守卫查不到（结构性的，⛔ 不是偏好）**

| 不进 | 为什么 |
|---|---|
| **`check_session_token_budget`（`B8`）· `circuit(global_key())`（`B11`）** | ① **触顶要回 4xx**，⛔ 不是「HTTP 200 + 流一半断」⇒ 必须在**建生成器之前**拒；② 两个 **AST 守卫钻进端点函数体**查它们（`api/test_session_budget_wiring.py:65` · `api/test_breaker_wiring.py:44`）⇒ 搬进共享层，**守卫查不到** = 「门挂在别处＝没有门」的变体 |
| **`register` / `resolve`（`B5` 待接管队列）** | 四条链各不同；且它们靠**模块全局**查找 ⇒ 挪进来 `monkeypatch` **就够不着了** |

**第二类：各链专有，进共享层就变成"猜"**

| 不进 | 为什么 |
|---|---|
| `summarize_agent_result` / status 口径 | 只有 Agent 链有 status；**`plan_execute` 根本没有** |
| `session_key` 拼身份 · 原 `thread_id` 回显 | ⚠️ **本仓有两条轴**：预算用**原值**、图用**拼过的** —— ⛔ **别合并**（合并要连追踪的读写一起改，那是另一件事） |
| 检索 / prompt 构建 / LLM 单例 | 各链专有 |
| **节点名** | 通过 `graph_message_text(..., nodes=…)` **由调用方传**；而**名单住在各自的图模块里**（见 3.4） |

### 3.3 一处**不显眼但会炸**的实现细节：`SSE_HEADERS` 必须 copy

`sse_response()` 里写的是 `headers=dict(SSE_HEADERS)`，⛔ **不是直接把模块级 dict 传进去**：
`StreamingResponse` 会**持有并改写**它自己的 `headers` ⇒ 共享同一个 dict 等于让**所有响应串台**，
而且是在「某天多了一条路由」时才炸。

### 3.4 可流节点名单住哪：**在图模块里，⛔ 不在端点里**

```python
# api/agent_graph.py —— 紧挨 workflow.add_node(...)
STREAMABLE_NODES = frozenset({"agent"})
```

端点只写 `nodes=agent_graph.STREAMABLE_NODES`，⛔ **不自己抄一份字面量**。
理由正是 `DEC-051` 的病根：**手工维护的映射必然与注册表漂移，而且那次漂移静默无效**。

⚠️ **必须放【模块级】**，放进 `build_xxx_graph()` 函数体就是**局部名**
⇒ 端点 `agent_graph.STREAMABLE_NODES` 直接 `AttributeError`
（本批**真的踩过一次**才改过来）。📌 守卫：`api/test_agent_stream_chains.py::test_chain_a_whitelist_is_the_graph_module_s_own`

---

## 四 · 四条链的形态**各不相同**（⛔ 本条最容易被当成"复制粘贴"的地方）

| 链 | 端点 | 图 / 实现 | 可流节点 | 形态 |
|---|---|---|---|---|
| **A** | `/agent/advanced_chat/stream` | `agent_graph_advanced_learning.py` | **4 个**（`chat` · `search_summarize` · `translate_execute` · `agent`） | **同步** `.stream` · 🔴 **必须 `subgraphs=True`**，否则**一个字都流不出来** |
| **B** | `/agent/memory_chat/stream` | `agent_checkpointer.py` | **1 个**（`agent_decide`） | **同步** `.stream` · ⚠️ 带 `interrupt_before=["approval"]` |
| **C** | `/agent/mcp_chat/stream` | `agent_graph_advanced.py` | **2 个**（`agent_decide` · `chat_node`） | ⚠️ **节点本来就是 `async def`** ⇒ 走 **`astream`**，⛔ 别照抄 A/B 的同步写法 |
| **D** | `/agent/plan_execute/stream` | **不是图**（`plan_execute.py` 的同步函数） | — | **`_ThreadTokenBridge`**（线程 → 事件循环） |

**共同的一条硬约束（⛔ 四条一条都不许违反）**：
**节点保持原样同步 / 异步，⛔ 不许把同步节点改成 `async def`** ——
`DEC-050` 实测：同步的 `graph.invoke()` 会当场抛
`TypeError: No synchronous function provided to "agent"`，而**非流式路径都在用它**。

### 4.1 链 A 的两条**现状**（⛔ 别当 bug 去"修"）

1. **CALC / DATE 两个意图【一个字都流不出来】** —— 它们的答案来自**工具返回值**
   （`calculator` / `date_today`），⛔ **不是 LLM 输出** ⇒ 用户会一直等到**末帧汇总**才看到 `answer`。
   ⛔ **别为了"看起来也在流"把 `calc_execute` 的表达式提取过程放出去** —— 那是中间产物。
   📌 判据：`agent_graph_advanced_learning.py` 里**调 LLM 的节点有 6 个，只有 4 个该流**
   （`supervisor` 流出去是**路由词**；`calc_execute` 流出去是**提取串**）。
2. **`supervisor` 的路由词（`SEARCH` / `CALCULATOR` / …）不会出现** —— 它**确实产块**，
   靠白名单挡掉。⚠️ **不是"它不产生块"**。
   ⚠️ **更隐蔽的一类**：返回 `messages`（或整个 state）的节点会**额外发一块「非 token 的整块」** ——
   实测 `supervisor`（它 `return state`）会把它收到的**用户提问原文**当"新消息"发出来
   ⇒ **不加白名单，用户会先看到自己的问题被回显一遍**。
   ⛔ **别用"这块是不是 token"当判据**（没有可靠的判别字段）⇒ **就按节点名收**。

### 4.2 链 D 的两条**推论**（业务方选「甲 · 照原样流 JSON」的直接后果）

1. **流内文本是【正在生成的 JSON 片段】，⛔ 不是人读终稿** ——
   `plan_task` 的提示词明确要求严格 JSON 输出（`plan_execute.py:216-222`），下游还要 `json.loads`。
   ⇒ 前端的正确用法 = 当**"规划中"指示器**；**终稿只看最后一帧**。
   ⛔ **不许把流到的 JSON 直接渲染成计划**（模型可能吐不完整 / 非法 JSON —— 正因如此 `plan_task` 才有那段兜底）。
2. **只有「规划段」在流** —— `execute_plan`（执行段）**不流**。
   ⇒ 规划段之后是**一长段静默**（N 步 × 每步 2 次 LLM），然后才是末帧。
   ⛔ **别让读者以为执行段也在流**（这条要如实写进 spec 与契约文档）。

⚠️ **链 D 的帧格式与 A/B/C 是同一套**（`{"content": …}` 逐块 + 末帧汇总 + `[DONE]`），
⛔ **没另发明**一种「JSON 流」格式 —— 共享层要能吃下它，这也是它用 `llm_chunk_text` 而非
`graph_message_text` 的原因（**它不是图**）。

---

## 五 · 两条旧端点改走共享层：**逐帧等价**，⛔ 不是"顺手统一"

| 端点 | 改前 | 改后 |
|---|---|---|
| `api_v1_agent.py::langgraph_chat_stream` | 内联生成器 ~60 行 | 调共享层，**留前置闸**与 `register` / `resolve` |
| `api_v1_rag.py::stream_search` | 内联生成器 ~80 行 | 调共享层，**留检索 / 提示词构造** |

**判据（可打印）**：**两份既有测试全绿，且这两个文件的 diff 为空**（`api/test_agent_sse.py` · `api/test_cancel_propagation.py`）。

🔴 **RAG 那条有【三处看着像 bug、但不能动】的地方** —— 全部由**调用方显式传入**，⛔ 没被"抽公共"抹掉：

| # | 现状 | 共享层怎么容下它 |
|---|---|---|
| 1 | **`[DONE]` 帧出现在 `sources` 帧【之前】**（`:738` vs `:748`） | 整条尾巴由 `on_complete` 产 ⇒ 骨架**不自动补 `[DONE]`** |
| 2 | **取消时【不发任何帧】** | 约束③（`CancelledError: raise`） |
| 3 | 每次 `yield` 后 `await asyncio.sleep(0.01)` **限速** | `chunk_delay=0.01` |

⚠️ **第 4 处是"编码"而非"顺序"**：RAG 那三帧**一直没传 `ensure_ascii`**（⇒ 中文变 `\uXXXX`），
而 `/agent/*` 四条链**一直是中文原样出**。**本轮【不统一】**，用 `ensure_ascii` 参数**把旧字节逐字留住**：

- 两种编码 **JSON 解码后的值完全相同**（前端都走 `JSON.parse`）⇒ **统一与否不影响功能**；
- 但**统一会让"逐帧等价"这句话从"字面为真"变成"差不多"**。
- ⇒ **已登记待裁**（见 §六·遗留 2）。

### 5.1 一处**日志文案的统一**（本次唯一的措辞改动，如实记录）

`/agent/langgraph_chat/stream` 取消时的日志原文是
「已停止生成并**关闭图的流**」；共享层写的是「已停止生成并**关闭上游流**」
（`api/sse.py:266`，与 `api/metrics.py:33` 的 counter 说明用词一致）。

- **为什么可以合**：⛔ **没有任何用例断言这句文案**（`grep -rn "已停止生成" api/` ⇒ 只有 `sse.py` 与 `metrics.py` 两处）。
- ⚠️ **为什么不加"兼容"**：为**没有消费者的旧措辞**保留分支，就是往共享层里塞特例。
- 📌 **判据（可打印）**：`grep -rn "已停止生成并关闭" api/ --include="*.py"` ⇒ **2 行**（`sse.py` 的日志 + `metrics.py` 的说明），
  **⛔ 没有第二份日志文案**。

---

## 六 · 遗留（**如实列出，⛔ 不假装已解决**）

| # | 事项 | 为什么不本轮做 |
|---|---|---|
| **1** | 🔴 **链 B（`/agent/memory_chat`）的记账【从来没执行过】** —— `agent_checkpointer.py:83` 判的是 `hasattr(response, "usage")`，而真 `AIMessage` **只有 `usage_metadata`、没有 `.usage`** ⇒ **恒为 False** | **修它 = 开始拦人，是【行为变更】**（配额从"形同虚设"变成"真拦"）⇒ **要单独裁**。📄 勘察 §8.5 |
| **2** | ⚠️ **`ensure_ascii` 两种口径并存**（RAG `True` / Agent `False`） | 见 §五 —— 统一会破坏"逐帧等价"。📌 **2026-10-10 已正式登记** ⇒ `docs/待办总表.md` **`N30`**（未裁） |
| **3** | ⚠️ **`api/agent_graph_advanced_learning.py:71` 的行内注释已过期** —— 它说捆绑的 `calculator` / `date_today` 在 `:145` / `:160` 调用，**实际是 `:170` / `:185`** | ⛔ **本 Agent 未改**（属"顺手清理"，用户明确拒绝）⇒ **报告，不动手**。📌 判据：`grep -n "tool_calls\[0\]" api/agent_graph_advanced_learning.py` 对 `:71` 那句 |
| **4** | ⚠️ **「其余 29 条端点不是缺口」是【本批的判断】，⛔ 没走业务裁定** | 硬门 A 要的是「**该**流的流」，「该不该」**得由业务方按端点定** ⇒ 已写进 `ROADMAP.md` / `docs/待办总表.md` / `docs/契约/接口契约.md` **三处**，每处都标了 |
| **5** | ⚠️ **`DEC-055`（中断 / 异常路径的留痕口径）的前提要按新数重核** —— 它普查时"3 条流式里只有 1 条是 LangGraph"，现在是 **6 条** | 那是**另一件事**的实现前提，⛔ 不在本轮范围。已在该条上加了提示 |

> 📌 **2026-10-04 评审收口（PR #78 合并前评审）—— 三件事，均已处理**（⚠️ **上面这张表没预见到它们**，如实补记）：
> ① **5 条流式端点的汇总帧都少 `requested_by`**（而非流式兄弟 5 条全有）⇒ **`DEC-060`**（已实施，`b0b1835`）；
> ② **`docs/specs/sse.md:31` 的判据是假的** —— 「44 passed」与该行的命令对不上
>    （44 = 当时那两份文件的 **29** + `api/test_sse_layer.py` 的 **15**）⇒ 已按**实测**更正（**31 passed**）；
> ③ **`api/agent_graph.py:225` 那句「判据」指向的用例【不存在】**（幽灵锚点）⇒ **`DEC-061`**（已实施，`c02638e`）。

---

## 七 · ⛔ 不做什么（以及理由，⛔ 不是"没时间"）

| 不做 | 理由 |
|---|---|
| **`/agent/approve` 加流式** | 业务方 2026-10-04 裁定。它是「续跑一个已停下的图」，不是「生成答案」 |
| **把同步节点改成 `async def`** | `DEC-050` 实测：同步 `graph.invoke()` 当场抛 `TypeError`，而**非流式路径都在用它** |
| **`content +=` 聚合** | 会丢**碎片化**的 `tool_calls` ⇒ `B4` 人工审批**静默失效**（`DEC-050`） |
| **另起一张「流式专用图」** | `DEC-050` 已否：一份图变两份 ⇒ 审批 / 队列 / 续跑要复制，且**会漂而没人发现** |
| **改 RAG 的帧顺序 / 编码 / 限速** | 见 §五 —— 抽公共层**不是**顺手改行为的理由 |
| **让 `calc_execute` / `supervisor` 也流** | §4.1：流出去的是**提取串**和**路由词**，不是答案 |
| **给 `plan_execute` 编一个 `usage_metadata`** | `plan_execute.py:148` 明文：「没有就**如实不记**，不编一个数字」 |

---

## 八 · 判据（**都可打印**）

```bash
# ① 4 条新路由真的注册了（⛔ 不看 header，数路由）
grep -c '"/agent/.*stream"' api/api_v1_agent.py          # ⇒ 5
grep -c '^@router' api/api_v1_agent.py                   # ⇒ 34

# ② 逐 token 一帧（真流式的判据是【块数】，⛔ 不是 content-type）
venv/bin/python -m pytest api/test_agent_sse.py api/test_agent_stream_chains.py api/test_sse_layer.py -q

# ③ 取消传播（关上游 + 计数 + 日志）—— 4 条新链各一条
venv/bin/python -m pytest api/test_cancel_propagation.py -q

# ④ 非流式路径没被弄坏
venv/bin/python -m pytest api/test_approval_resume.py api/test_tool_dispatch.py api/test_agent_repairs.py -q

# ⑤ 两个新 spec 都在
# ⚠️ 必须带 `--missing`：不带参数时 `spec_status.sh` **只列"没 spec"的前 15 个**
#    （它就是那张缺失清单），**有 spec 的模块一个都不列** ⇒ 加 `grep` 恒为空，判据是假的。
bash scripts/spec_status.sh --missing | grep -E "sse|advanced_learning"   # ⇒ 无输出（rc=1）= 两份都不在缺失清单里
ls -1 docs/specs/sse.md docs/specs/agent_graph_advanced_learning.md       # ⇒ 两份都在（直接证据）

# ⑥ 路由鉴权没漏
venv/bin/python scripts/check_route_auth.py --baseline   # ⇒ ✅ 与基线一致（63 APIRoute / 10 无鉴权）

# ⑦ CI 口径（⚠️ 本机 postgres 开着 ⇒ 裸 pytest 会【假绿】）
POSTGRES_PORT=59999 venv/bin/python -m pytest api/ -q -m "not integration and not needs_db"
bash scripts/ci-local.sh
```

**真服务（必须 —— `DEC-050` 的教训：`TestClient` 抓不到真服务的取消行为）**：
起 uvicorn + `curl -N` 打 4 条新路由，逐条核对 **帧数 ≥ token 数** 且**时间戳递增**；
断开时核对 `stream_cancelled_total{endpoint="…"}` 计数 **+1** 且日志有 `[cancel]` 行。

---

## 关联

- `docs/decisions/DEC-050-真流式的条件是节点转发config.md` —— **真流式的必要条件**（本条的立论基础）
- `docs/decisions/DEC-051-工具名分派与审批白名单的标识符勘误.md` —— **"名字只能有一个来源"**
  ⇒ 本条的 `STREAMABLE_NODES` 放图模块、⛔ 端点不抄字面量，就是这条教训的直接应用
- `docs/decisions/DEC-052` / `DEC-054` —— 约束 ① ② ③ 的出处（取消传播 / 收尾顺序 + 关流护盾）
- `docs/specs/sse.md` —— 本模块的 spec · `docs/specs/agent_graph_advanced_learning.md` 的 ⭐ 节（6 个调 LLM 的节点只有 4 个该流）
- `docs/契约/接口契约.md` §流式端点 · `ROADMAP.md` 功能现状表「SSE 流式（Agent 端）」· `docs/待办总表.md` **B1**
