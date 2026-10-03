# `api/api_v1_agent.py`

| 项 | 内容 |
|---|---|
| **状态** | 🟡 **可用；流式【有了第一条】**（`③` Task 4 · `B1` · 2026-10-03）—— ⚠️ **但只有 `/agent/langgraph_chat/stream` 这一条**，其余 **29 条仍全非流式**<br>🔵 **改造中**：本文件下方有 **实施计划 ②**（人工接管 · **已完成**）与 **③**（流式与取消 · **进行中，还剩 `B2`/`B3`**）<br>✅ **2026-10-03（`②` Task 2 · `B5`）**：新增 **`GET /agent/pending`** ⇒ 路由 **28 → 29**<br>✅ **2026-10-03（`②` Task 3 · `B6`）**：`POST /agent/approve` 增加可选参数 **`edited_answer`** ⇒ **硬门 D 三段齐了**<br>🔵 **2026-10-03（`③` Task 4 · `B1`）**：新增 **`POST /agent/langgraph_chat/stream`**（SSE）⇒ 路由 **29 → 30**。📄 `DEC-050`<br>✅ **2026-10-03（`③` Task 5 · `B2`）**：新加的这条流式路由**补上了 cancel 传播**（关图的流 + 记数）—— `DEC-050` §遗留·3 自己点的那个洞**已堵**。📄 `DEC-052`<br>🔴 **2026-10-03（`DEC-056` 丙段）· 三条口径变了**：<br>① **进图的 checkpoint 键**由裸 `thread_id` 改成 **`session_key(user_name, thread_id)`**（4 张图 · 7 处）；⚠️ **响应仍回显原值**<br>② **`/agent/approve` 加了归属校验**（**本人或 admin**）+ **按登记表里的 `graph` 字段路由**；⛔ 它**不再**直接吃 `agent_graph` 写死<br>③ **`/agent/memory_chat` 接上审批门**（`interrupt_before=["approval"]`）⇒ **`DEC-051` §遗留·2 关闭** |
| **对外提供** | 30 个路由（`/agent/langgraph_chat` · **`/agent/langgraph_chat/stream`** · `/agent/approve` · `/agent/pending` · `/agent/mcp_chat` · `/agent/advanced_chat` · `/agent/plan_execute` · `/agent/token/*` …）· `summarize_agent_result()` |
| **谁在用** | 前端（未做）· `test_public_paths.py` 等 |
| **规模** | **1007 行**（`scripts/spec_status.sh` 口径 = **本仓口径**；`wc -l` 报 **1006** —— 本文件**末行没有换行符** ⇒ 少算 1，⛔ **不是笔误**，同 `agent_graph.py`）<br>⚠️ **别抄这个数** —— 它当天已被重取过**五次**：743 → 835 → 875 → 894 → **1006/1007** |

## ✅ 做了什么

- **对话链**：`langgraph_chat`(:84) · `advanced_chat`(:154) · `plan_execute`(:183) · `memory_chat`(:227) · `mcp_chat`(:450)
  · 🔵 **B8（2026-10-01）**：这 5 条**全部接上会话级 token 上限**（`check_session_token_budget`），触顶抛 `QUOTA_EXCEEDED`
- **人工审批**：`POST /agent/approve`（`:151`）—— 批准 / 拒绝 / **改写后提交**，靠 `agent_graph` 的 `interrupt_before`
  · 🔵 **改写后提交（`②` Task 3 · `B6` · 2026-10-03）**：可选参数 **`edited_answer`（`:155`）**。
    **批准 ∧ 给了改写** ⇒ 先 `update_state` 把它推成一条 **`AIMessage`**，再 `invoke(None, config)` 续跑；
    **不给** ⇒ 走原来的 `update_state(values=None)`（行为与改动前一致）；**拒绝** ⇒ 给了也忽略。
  · ⭐ **续跑形状被测试钉住**：`api/test_approval_resume.py`（6 条 · **纯离线 · 进 CI**）——
    `invoke` 必须是 **`None`**（= 从 checkpoint 继续，⛔ 不是新开一轮）、`config` 必须是**请求里那个 thread_id**
- 🔵 **待接管队列（`②` Task 2 · `B5` · 2026-10-03）**：新增 **`GET /agent/pending`** —— 列出**当前在等接管的会话**
  （事实来源 = 新模块 **`api/pending_approvals.py`**，⛔ **不是从 checkpoint 反查** —— `MemorySaver` **没有"列出全部 thread"的 API**）。
  `langgraph_chat` 在拿到 `summary` 后**登记 / 注销**，`approve_agent_action` 在**每条 return 前**注销。
- **⭐ `summarize_agent_result()`（`:43`）** —— 把图的运行结果翻成 `{"status": "pending_approval"/"answered", …}`，
  并**把模型已写出的文字一并返回**（真实 LLM 常"先说一句再调工具"）
- **预算**：`check_budget` 依赖（`:423`，抛 `AppException(QUOTA_EXCEEDED)`）· 6 个 `/agent/token/*` 查询路由
- 🔵 **成本可见两处（`①b` Task 7 · `B13` · 2026-10-03 · `DEC-047`）**：
  · **`/agent/token/budget`（`:492`）** 补上**全站日级**三个字段（`global_daily_limit` / `global_used_today` / `global_remaining`）——
  在此之前 `B10`/`B11` 的全站额度**只有入口没有出口**，超了所有人吃 429 却**界面上看不到逼近**；
  · **`/agent/cost/overview`（`:658`）** 数据源从 **`get_user_summary`（进程内存）** 换成 **`get_user_overview`（读库）**，
  `by_purpose` 随之从**全站**变**本人**
- 🔵 **Agent 端 SSE（`③` Task 4 · `B1` · 2026-10-03 · `DEC-050`）**：新增 **`POST /agent/langgraph_chat/stream`**
  （紧跟在 `/agent/langgraph_chat` 之后）—— **本文件的第一条、也是目前唯一一条真流式路由**。
  · **帧格式**：逐 token 一个 `data: {"content": "..."}`，最后一个是 `data: {…summary}`（含 `thread_id`/`status`/`answer`），
    再 `data: [DONE]`；出错则 `data: {"error": "..."}` + `[DONE]`。
  · **它真流式靠的是 `agent_graph.py` 那一侧**（`agent_decide` 声明 `config` + 转发 `.stream(config)`）——
    ⛔ **本文件这边只负责"转发"**，接线错了接口**照样长得像流式**。📄 见 `docs/specs/agent_graph.md`
  · ⚠️ **三条接线必须一致**：`stream_mode="messages"` · `meta["langgraph_node"] == "agent"` · **两条前置闸**
    （`check_session_token_budget` `B8` + `circuit(global_key())` `B11`）与 `/agent/langgraph_chat` **同源**
  · ⭐ **判据**（可打印）：`api/test_agent_sse.py`（12 例 · **纯离线 · 进 CI**）
  · ⚠️ **`X-Accel-Buffering: no` 是必须的** —— 少了它，Nginx / Cloudflare 会把整段缓冲住 ⇒ **又变回假流式**（本仓要上 Cloudflare 隧道）
- **工具**：`/agent/tool_health` · `/agent/tool_versions` · `/agent/available_tools` · `/agent/mcp_tools_dynamic`

## 🟡 做到哪 / 缺什么

- 🔵 ~~**29 个路由全非流式** ⇒ **硬门 A 的缺口**~~ ⇒ **2026-10-03 起缺口【开了一条】**（`③` Task 4 · `B1`）：
  新增 `/agent/langgraph_chat/stream`。⚠️ **但只有这一条** —— **其余 29 条仍全非流式**，
  硬门 A 要的是"**该流的流**"，⛔ **不是"流了一条就算完"**。📄 `DEC-050`
  · ✅ ~~⚠️ **`B2`（cancel 传播到上游）**~~ ⇒ **2026-10-03（`③` Task 5）【已做】** ——
  客户端断开 ⇒ 关掉图的流（`aclose()`）+ 记 `stream_cancelled_total`。📄 `DEC-052`
  · ✅ ~~**`B3`（半截答案怎么处理）【仍未做】**~~ ⇒ **2026-10-03（`③` Task 6）已裁**：「**存**」，
    提问 + 半截 + 中断标记（`DEC-053`）。⚠️ **Agent 端这边不用改** —— 它的半路状态由 checkpointer 持有
- ✅ ~~🔴 **没有「待接管队列」端点**~~ ⇒ **2026-10-03 起【有了】**（`②` Task 2 · `B5`）：`GET /agent/pending`。
  ⚠️ **但队列背后是【进程内存】**（`api/pending_approvals.py`）⇒ **重启即空** —— 见其 spec 里那条"已知限制"
- ✅ ~~**`B6`（接管后续跑）未做**~~ ⇒ **2026-10-03 起【已做】**（`②` Task 3）：`edited_answer` 改写后提交 + 续跑形状被 `test_approval_resume.py` 钉住。
  ⚠️ **但只是"接线与语义"层** —— **真跑一遍"上下文确实连续"（真 LLM + 真 MemorySaver）没有测**，
  那需要联网花钱（见该测试文件的 docstring：本文件测的是**接线**，不是模型质量）。
- 🔴 **`/agent/approve` 的参数是 query 不是 body**（`:152-155`，**含新的 `edited_answer`**）⇒ 前端联调会踩
- 🔴 **`/agent/cost/overview` 的三个总数曾经是【进程内存】**（2026-10-03 修，`DEC-047`）——
  它**不报错、界面照常出数**，只是**重启后答 0**（实测库里有 4216 tokens、它答 0）。
  ⚠️ **同族的仍在**：`/agent/token/overview` · `/agent/thread/{id}/overview` · 看板第 2 格
  **都是内存口径**（语义 = "本进程"，**有意保留**，⛔ 别当 bug 删）
- ⬜ 零散的 `/agent/token/*` 与 `/agent/cost/*` 有重复嫌疑（**未核**；⚠️ `DEC-047` 已把口径说清：
  `/agent/token/budget` = **今天 + 还剩多少**，`/agent/cost/overview` = **全时一共**，两者**不重复**）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴🔴 **「`/agent/langgraph_chat/stream` 的结尾那个 `summary`，把流过 `agent` 节点的块攒起来算就行」** | ⛔ **不行，会算错**（2026-10-03 **真服务**撞见，`③` Task 4）。<br>**攒块 = 跨多轮累积** —— 模型因工具返回"未找到工具"而**重试**时，`agent` 节点会进**多次** ⇒ 攒出来的东西带着**上一轮的** `tool_calls` ⇒ `summarize_agent_result` 报 **`pending_approval`，而图其实已经跑完**（前端会**永远等一个不会来的审批**）。<br>⚠️ 实测症状：`tool_calls` 的 name 被**拼接**成 `"date_todayduckduckgo_search"`。<br>🔴 **2026-10-03（`DEC-051`）**：那次"反复重试"的**根因已修**（`tool_execute` 原来是按字面量 `"search"` 分派、真名是 `duckduckgo_search`）⇒ ⚠️ **但本行仍照旧成立** —— 只要端点还在拿流式块猜，**任何**多轮场景都会重演。<br>✅ **正确做法：从图的最终状态取** —— `await agent_graph.aget_state(config)` ⇒ `summarize_agent_result(state.values)`，与 `/agent/langgraph_chat` **完全同一套语义**。<br>📌 判据（可打印）：`api/test_agent_sse.py::test_status_comes_from_final_state_not_from_streamed_chunks`（`_TwoRoundModel` 逼出第二轮） |
| 🔴 **「这条流式端点没有 cancel 处理」** | ✅ **2026-10-03（`③` Task 5 · `B2`）起【有了】** —— 客户端断开后**关掉图的流**（`finally` 里 `await stream.aclose()`），并记 `stream_cancelled_total{endpoint="agent_langgraph_chat_stream"}`。<br>⚠️ **不关的代价是"图继续跑完"** = 继续调模型 = **继续烧钱**，而前端看起来一切正常（它只是不显示了）。<br>⚠️ **本轮之前这里确实是空的** —— 而且 `DEC-050` §遗留·3 **自己点了名**。<br>🔴🔴 **2026-10-03 补（`DEC-054`）**：`finally` 里的**顺序**与**关流方式**当天下午被真服务推翻过一次 —— `await stream.aclose()` **会被二次投递的取消打断**，排在它后面的收尾**一件都不跑**（本端点症状：**计数不涨、`[cancel]` 日志没有**）。<br>✅ 现在：**同步收尾提到任何 `await` 之前** + 关流包 `anyio.CancelScope(shield=True)`。⛔ **别改回去**（"关流是收尾动作、放最前面才干净"正是那个坏改法）。<br>⚠️ **注意本端点与 `/rag/stream_search` 的差别**：本端点取消时**一条历史都不留**（那是 `DEC-055` 的事，⬜ 未实施）。<br>📌 判据（可打印）：`api/test_cancel_propagation.py` ⇒ **17 passed**（`B2` 10 · `B3` 3 · 10-03 真服务复现 4）；真服务 = 计数 +1 且日志有 `[cancel]` 行 |
| 🔴 **「客户端断开得靠 `request.is_disconnected()` 自己轮询」** | ⛔ **不用，那是框架给的**（uvicorn 报 `spec_version 2.3` ⇒ Starlette 监听 `http.disconnect` 后**取消生成器**）。<br>⇒ 真正的缺口只有「**停下并关掉上游**」这一件；**自己加轮询 = 多余，且会掩盖真缺口**（`DEC-052`） |
| 🔴 **「中间件日志里那个秒数 = 这条流的生成耗时」** | ⛔ **不是** —— 它记到**响应开始返回**为止。实测：`(0.019s)` 的那条客户端收了 **27KB**、`(0.004s)` 的那条 **3 秒后**才 cancel。<br>⇒ ⛔ 别拿它当"生成提前停了"的证据（第一版就这么误读过 · `DEC-052`） |
| 🔴 **「`status=answered` 就是拿到最终答案了」** | ⚠️ **要看 `status`** —— 返回 `pending_approval` 时 `answer` 里是**模型"先说的一句"**，**工具还没执行**。`summarize_agent_result` 的 docstring（`:55-80`）专门讲了这点：**不能加 `and not content`**，否则这种形态会被**误报成 `answered`**。⚠️ **该 docstring 还写了这条判据"依赖什么、什么时候会失效"**（B4 后理由变了）—— 改图的路由时**要回去重看** |
| ⚠️ ~~🔴 **「审批已经能用了，硬门 D 算完成」**~~ | ✅ **2026-10-03（`②` Task 1 · `B4`）改了口径**：**触发条件不再是「任意 `tool_calls`」**，而是**工具白名单**（`agent_graph.py` 的 `SENSITIVE_TOOLS`）⇒ **问个日期不再进审批**。<br>🔴 **但白名单里的名字当时写错了**（`search_tool` 是**变量名**）⇒ **交集恒空 ⇒ 审批其实【永不触发】**，**直到 2026-10-03 才由 `DEC-051` 修掉**。⇒ ⚠️ **"改了口径"与"口径真的生效"是两件事** —— 前者当天就成立了，后者晚了三天。<br>✅ **2026-10-03（`②` Task 2/3）：`B5` 队列 与 `B6` 续跑都【已做】** ⇒ **三段（什么时候停 / 停在哪看得到 / 批了怎么接着跑）齐了**。<br>⚠️ **但"齐了"≠"验收过"**：`B6` 只钉了**接线与语义**（`invoke(None)` + `edited_answer` 进 `AIMessage`），<br>**"上下文真的连续"没有端到端跑过**（要真 LLM + 真 `MemorySaver`，**联网花钱**）⇒ 验收演示时**要补那一步**。<br>⚠️ **本条 2026-10-03 之前写的是旧口径**，⛔ 别照旧理解 |
| ⚠️ **「`/agent/approve` 收 JSON body」** | ⛔ **不是** —— `thread_id` / `approved` / **`edited_answer`** **都是 query 参数**（`:152-155`） |
| 🔴🔴 **「`/agent/approve` 拿 `thread_id` 就能批」** | ⛔ **2026-10-03（丙段）起不能了** —— 它现在**先从待接管队列反查属主**，再判**本人或 admin**。<br>⚠️ **改之前它没有任何归属校验** —— 任何人拿一个 `thread_id` 就能**批准并续跑**那个会话。<br>🔴 **为什么不能"按调用方拼"**：`/agent/pending` 是**跨用户队列**（硬门 D）⇒ 按调用方拼，admin 会拼出 `admin:…`、属主是 `alice:…` ⇒ **admin 永远批不了别人的**。<br>⚠️ **代价（知道再选）**：**队列是唯一入口** ⇒ `AGENT_CHECKPOINT_BACKEND=sqlite` 重启后（图在盘上、队列在内存）会答"没有待审批任务"，而以前能批。📌 判据 ⇒ `api/test_approve_ownership.py` |
| 🔴 **「`/agent/approve` 只认 `agent_graph`」** | ⛔ **两张图** —— `/agent/langgraph_chat` 走 `agent_graph`、**`/agent/memory_chat` 走 `checkpointer_agent`**（丙段给它加了审批门）⇒ approve **按登记表里的 `graph` 字段路由**。<br>⚠️ 写死 `agent_graph` 的后果：memory_chat 那条会话**永远放行不了**（**门关了却没有钥匙**，比不加门还糟）。业务方 2026-10-03 裁。📌 判据 ⇒ `api/test_memory_chat_approval.py::test_approve_routes_to_checkpointer_graph` |
| 🔴 **「`memory_chat` 没有审批门」（2026-10-03 前的口径）** | ✅ **丙段起有了** —— `checkpointer_agent` 带 `interrupt_before=["approval"]`，敏感工具会停下。⚠️ **输出形状也变了**：新增 `status` / `pending_tool_calls`（与 `/agent/langgraph_chat` 一致，⛔ 不再返回 200 + 空答案） |
| ⚠️ **「`thread_id` 拼身份 = 全仓统一拼法」** | ⛔ **不是** —— checkpoint 轴用 `session_key()`（**长度前缀**，无歧义）；而 **`:612`（`add_memory`）与 `:628`（`search_memory`）那两处 `f"{user_name}:{memory_space}"`** 仍是**朴素拼接**（含 `:` 会有歧义）。⚠️ 两条轴**各有各的拼法**，丙段**只动了 checkpoint 那条** |
| 🔴 **「`edited_answer` 就是"把答案改一下再返回"」** | ⛔ **不止** —— 它**先写进 graph state**（`update_state` → `AIMessage`），**再从 checkpoint 续跑**。<br>⚠️ **差别在哪**：审批之后图**还要去 `tools` → `agent`** ⇒ 只把改写当返回值吐出去，**后续节点看不到它**（改写等于没改）。<br>⚠️ **必须是 `AIMessage`**：用 `HumanMessage` 会让模型把"人给的结论"当成**用户新提的问题**再答一遍 |
| ⚠️ **「审批状态是持久化的」** | ⚠️ **默认不是** —— `agent_graph.py:179` 用的是 `MemorySaver()`（**进程内存**）⇒ **重启即丢**。只有设了 `AGENT_CHECKPOINT_BACKEND=sqlite` 才落盘 |
| 🔴 **「`check_budget` 就是会话上限」** | ⛔ **不是** —— `check_budget`（`:426`）判的是**用户【每日】token 预算**。**会话级是另一个函数**（`check_session_token_budget`，B8 · 2026-10-01）。两者**并存**，⚠️ `/agent/mcp_chat` 上**两条都挂** |
| 🔴 **「会话上限没拦住 = 没生效」** | ⚠️ **先看 `thread_id` 是不是默认值** —— 会话 key = **`user_name` + `thread_id`**（`DEC-041` 决策二）。<br>4 个端点的 `thread_id` 默认 `"default"` ⇒ **同一个人的**多次默认调用**共用**一个桶（**不同人不会互相踩** —— 这正是决策二加 `user_name` 的原因）。<br>⚠️ 但**换个 `thread_id` 就是换个桶** ⇒ 这是**设计如此**，不是漏拦<br>✅ **2026-10-03 起两条轴终于一致了** —— **checkpoint 那条轴**原先按**裸 `thread_id`** 走（`DEC-056` §二 根因），现在也拼 `user_name`（丙段）。⚠️ 但**拼法不同**（这条是 `f"{user}:{thread}"`，那条是长度前缀）⇒ ⛔ 别以为能互推 |
| ⚠️ **「`/agent/plan_execute` 一直有 `thread_id`」** | 🔴 **2026-10-01 才补的**（B8）。此前它**没有**这个参数 ⇒ 老客户端不传也能跑（走默认值），**行为不变**；但**新加的这条上限**在它上面用的是 `"default"` 桶 |
| ⚠️ **「额度是按人算的」** | ⚠️ **两者都是，但维度不同**：`check_budget` = 人 × 日；`check_session_token_budget` = **人 × 会话 × 日**。⛔ 别把其中一个当另一个 |
| 🔴 **「`/agent/traces` 是管理员看板」** | ⛔ **默认只给你本人的**（2026-10-03 之前**是**给所有人的 —— 见下一条）。看全量要 admin，而那个开关在端点里**显式一行**（`include_all=get_user_role(...) == UserRole.ADMIN`）。📌 判据 ⇒ `api/test_trace_isolation.py` |
| 🔴 **「`/agent/trace/{thread_id}` 拿一个 id 就能查」** | ⛔ **2026-10-03 起要属主**（`DEC-056` **决策 9** / N4）。改之前它**不判属主**，且轨迹存储**只按裸 `thread_id`** 做键 ⇒ 而本文件 4 个端点的 `thread_id` **默认就是 `"default"`** ⇒ **不传的人共用一个槽、后问的盖先问的**（⚠️ 与上面「会话上限」那条的桶碰撞**是同一个形状，但在另一条轴上**）。<br>⚠️ **非属主与"真不存在"答同一个**（`未找到线程 …`）—— **有意的**，否则那句错误本身就是"该 thread 存在"的 oracle |
| 🔴 **「`/agent/cost/overview` 答 0 ⇒ 没花过钱」** | ⛔ **先想想进程重启过没有** —— **2026-10-03 之前**它读 `get_user_summary` = **进程内存**，**重启即归零、且不报错**。<br>✅ 现在读 **`get_user_overview`（库）**，扛得住重启（`DEC-047`）。<br>⚠️ **但同族的三个仍然是内存**：`/agent/token/overview` · `/agent/thread/{id}/overview` · 看板第 2 格 —— **答 0 是真的 0，还是刚重启，看代码分辨不出来** |
| 🔴 **「`/agent/cost/overview` 和 `/agent/token/budget` 在报同一件事」** | ⛔ **不是，窗口不同**（`DEC-047` 特意划清的）：<br>`/agent/token/budget` = **今天 + 还剩多少**（`R1.3` 额度口径，**跨天自愈**）<br>`/agent/cost/overview` = **全时累计 + 一共多少**（字段名 `total_*`）。<br>⚠️ 两个口径**方向相反** ⇒ 若把 `overview` 的 SQL 加上 `created_at >= CURRENT_DATE`，它会**静默退化成"今天"**（数值偏小、不报错）。<br>📌 判据（可打印）：`api/test_cost_visibility_db.py::test_overview_window_is_all_time_not_today` |
| ⚠️ **「`/agent/token/budget` 的数是【本人】的，那就跟全站无关」** | ⚠️ **2026-10-03 起它同时答两层**（`DEC-047`）：本人（`daily_budget`/`used_today`/`remaining`）**和**全站（`global_daily_limit`/`global_used_today`/`global_remaining`）。<br>⚠️ **字段名不带 `global_` 前缀的那三个是本人的** —— ⛔ **别拿未加前缀的 `remaining` 当全站余量**。<br>📌 理由：**"还剩多少"必须能同时看到本人和全站**，否则看到 `999961` 也不知道那是谁的上限 |
| ⚠️ **「全站额度快满了，接口会给个预警」** | ⛔ **不会** —— 全站额度超了是**所有人吃 429**（`B11` 熔断），**没有"快到阈值了"的软提示**。<br>✅ 现在能**看到逼近**（`global_remaining`），但**得自己去看** —— ⬜ 无主动告警，`DEC-047` §遗留未列，本行仅备查 |

## 关联

`docs/specs/agent_graph.md`（审批节点的本尊）· `docs/specs/agent_checkpointer.md` ·
`docs/specs/api_v1_rag.md`（③ 的另一半）· `docs/specs/main.md` ·
`docs/specs/token_tracker.md`（**`get_user_overview` 的本尊** + 内存/库两套口径的说明）·
**`DEC-047`**（`①b` Task 7：`/agent/token/budget` 补全站字段 · `/agent/cost/overview` 换数据源）·
**`DEC-048`**（`②` Task 1 · `B4` 审批触发条件改工具白名单）·
🔴 **`DEC-051`**（**工具名分派与白名单的标识符勘误** —— 本节顶部那个勘误框、以及上面那条"名字写错了"的来源）·
**`DEC-050`**（`③` Task 4 · `B1` Agent 端 SSE —— 真流式的唯一条件 + `aget_state` 那个修正）·
**`docs/specs/pending_approvals.md`**（`②` Task 2 · `B5` 的队列模块）·
**`docs/specs/agent_graph.md`**（审批那一侧 · **也是 B1 流式的另一半**）·
🔴 **`DEC-056` 丙段**（**checkpoint 键拼身份** · **`/agent/approve` 归属校验 + 按图路由** · **`memory_chat` 审批门**）·
**`docs/specs/session_key.md`**（**键就是它拼的** —— 丙段新增模块）·
`后端补齐清单` **B1 · B2 · B3 · B4 · B5 · B6 · B13**

---

# 🔵 实施计划 ② · **人工接管**（2026-09-30 立 · **2026-10-03 执行中**）

> ## 📊 进度（2026-10-03）
>
> | | Task | 状态 |
> |---|---|---|
> | ✅ | **Task 0** · 前置决策（白名单里放哪些工具） | **业务方 2026-10-03 已答** = ~~`{search_tool}`~~ → **`{web_search}`** · `.env SENSITIVE_TOOLS`（见 `DEC-048`；🔴 **标识符已由 `DEC-051` 勘误**） |
> | ✅ | **Task 1** · `B4` 触发条件改工具白名单 | **已落地**（`DEC-048`）—— 判据：`pytest api/test_approval_trigger.py -q` ⇒ **7 passed** |
> | ✅ | **Task 2** · `B5` 待接管队列（数据 + 端点） | **已落地** —— 判据：`pytest api/test_pending_approvals.py api/test_pending_approvals_wiring.py -q` ⇒ **13 passed** |
> | ✅ | **Task 3** · `B6` 接管后续跑（含改写后提交） | **已落地** —— 判据：`pytest api/test_approval_resume.py -q` ⇒ **6 passed** |
>
> ⇒ **`②` 的 4 个 Task（0–3）全部落地** ⇒ **硬门 D 三段齐了**。
> ⚠️ **但"齐了"≠"验收过"** —— `B6` 只钉了**接线与语义**（假图），
> **"上下文真的连续"仍需一次真 LLM 端到端演示**（⛔ 本条别读成"硬门 D 已验证"）。

> ### 🔴🔴 **勘误（2026-10-03 · `DEC-051`）—— 读本节之前先读这一段**
>
> **本节正文（Task 0 的裁定表、Task 1 的逐 Step 代码块）是【当时的计划原文】，⛔ 别照抄。**
> 里面那个白名单名字 **~~`search_tool`~~ 是错的** —— 它是**变量名**，不是工具名
> （真名原为 `duckduckgo_search`，现随 `DEC-051` 换成 **`web_search`**）。
>
> | 本节写的 | 现在的实际 |
> |---|---|
> | `SENSITIVE_TOOLS` 默认 `"search_tool"` | **`"web_search"`**（`api/agent_graph.py:68`） |
> | `validate_approval_config()` **只查"非空"** | **两段** —— 空名单 **+ 名字不存在**，都 `raise`（`:73`） |
> | `tool_execute` 判 `if tool_name == "search"` | **查 `TOOLS_BY_NAME` 表**（`:172`），⛔ 不再有字面量 |
> | 工具 = `DuckDuckGoSearchRun()` | **`search_tools.web_search`**（Bing 版） |
>
> ⚠️ **后果**：按本节原文落地的那一版，**审批从来没触发过**（交集恒空）而**没有任何报错**。
> 📄 全文（含"为什么连测试文件自己都钉着错名字"）⇒ `docs/decisions/DEC-051-工具名分派与审批白名单的标识符勘误.md`
> 📌 **现在 `agent_graph.py` 长什么样**，以 `docs/specs/agent_graph.md` 为准（本节是**记录**，不是规范）。

> **来源**：`后端补齐清单-待裁-20260929.md` 的 **B4 · B5 · B6**（**业务方已裁：全部为「甲」**）。
> **三者是同一件事的三段**：**什么时候该停（B4）→ 停在哪看得到（B5）→ 批了怎么接着跑（B6）**。

**目标**：让硬门 D 从「**有地基、但语义是错的**」变成「**该转人工时才转，且转过去看得见、批完接得上**」。

**架构**：B4 改 `agent_graph.py` 的**条件边**（`should_continue` 从"有没有 tool_calls"改成"在不在敏感白名单"）；
B5 新增一个**待接管注册表** + 一个查询端点；B6 给 `/agent/approve` 加**改写后提交**。

---

## Task 0 · **前置决策**：白名单里放哪些工具？· ✅ **已答（2026-10-03）**

> `决策二` 已裁「**工具白名单**」，但**"白名单里放哪些工具"这个子问题还空着**。
> ⬜ **我不替你定** —— 但把判断材料摆出来：

| 工具 | 有没有**外部副作用** | 建议 |
|---|---|---|
| ⭐ ~~**`search_tool`**~~ → **`web_search`**（原 `DuckDuckGoSearchRun`，`DEC-051` 换成 Bing 版） | 🔴 **有** —— **它把查询内容发到第三方** | ✅ **放进白名单**（🔴 **写 `web_search`，⛔ 不是 `search_tool`**） |
| `calculator` | ⛔ 无 —— 纯本地计算 | ❌ 不放 |
| `date_today` | ⛔ 无 —— 纯本地取时间 | ❌ 不放 |

> ### ⇒ 我的建议：**白名单第一版 = ~~`{search_tool}`~~ → `{web_search}`**
>
> **理由**：**"敏感操作"的现实定义就是"会对外产生副作用"** —— 而 ~~`search_tool`~~ **`web_search`**
> **会把用户的问题原文发给搜索引擎**。这**不是"贵不贵"的问题，是"数据出去了"的问题**。
> ⚠️ **判据（`DEC-048` 的原话）一条都没变，改的只是那个名字** —— 见本节顶部的勘误框。
> ⚠️ 而 `calculator` / `date_today` 是纯本地的，**审批它们只会让人烦**（现状就是这个问题）。
>
> ### 🔴 而「空白名单」这个状态**必须明确表态**（三方文档都指出来了）
>
> 若白名单为空 ⇒ `needs_approval` 恒 `False` ⇒ **审批永不触发** ⇒
> **硬门 D 变成"有地基但从不启用"** —— 那是**验收上过不去**的。
> ⇒ **不许让它悄悄为空。** 见 Task 1 的 Step 4（启动时校验）。

- [x] **Step 1**：把「白名单第一版放哪些工具」的裁定写进 `后端补齐清单` 的 **B4 · ✍️ 裁**栏，再开工。

---

## Task 1 · **B4** · 触发条件改成「工具白名单」· ✅ **已落地（2026-10-03）**

> ⚠️ **落地时与计划有两处不同**（都记在 `DEC-048` 与 `CHANGELOG`）：
> ① **多写了 2 条测试**（计划 5 条 → 实际 7 条）：`validate_approval_config()` 的**正反两条** ——
>    只测"空了会炸"**可能误报**（判据写反、恒炸）。
> ② **顺手修了三处"改完就成假话"的注释/spec** —— 其中 `summarize_agent_result` 的 docstring
>    **判据的【理由】变了、结论没变**：改前「有 `tool_calls` ⇒ 一定停在审批」，
>    改后「**非敏感的 `tool_calls` 不会出现在返回态里**」⇒ 重写了它**为什么还成立**、**什么时候会失效**。


**Files:**
- Modify: `api/agent_graph.py`（`should_continue` `:95-103` · 条件边 `:130-137`）
- Test: `api/test_approval_trigger.py`（新建）
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `SENSITIVE_TOOLS: frozenset[str]` —— 从 env `SENSITIVE_TOOLS`（**逗号分隔的工具名**）
- Produces: `needs_approval(tool_calls: list[dict]) -> bool`
- ⚠️ `should_continue` 的返回值**从 2 种变 3 种**：`"approval"` / `"tools"` / `END`

- [x] **Step 1: 写失败测试**

```python
# api/test_approval_trigger.py
"""硬门 D 的触发条件（B4）。

🔴 改前的现状：**只要产生任意 tool_calls 就进审批** ⇒ 问一句"今天几号"也会停下来等人批。
   那条路在验收上是**过不去**的 —— 硬门 D 要的是「**该被接管时被接管**」，不是「全都接管」。

⚠️ 不碰 DB / Redis / 网络 —— 只测路由函数的返回值。
"""
import os

os.environ.setdefault("SENSITIVE_TOOLS", "search_tool")

from agent_graph import needs_approval, should_continue           # noqa: E402


def _calls(*names):
    return [{"name": n, "args": {}} for n in names]


def test_local_only_tools_do_not_need_approval():
    """🔴 本条对应"问个日期也进审批"那个现状 —— 它必须**不**触发。"""
    assert needs_approval(_calls("date_today")) is False
    assert needs_approval(_calls("calculator")) is False


def test_external_side_effect_tool_needs_approval():
    """`search_tool` 会把问题发到第三方 ⇒ 是敏感操作。"""
    assert needs_approval(_calls("search_tool")) is True


def test_mixed_calls_need_approval():
    """只要**有任何一个**敏感 ⇒ 整体审批（不能"挑着执行"）。"""
    assert needs_approval(_calls("date_today", "search_tool")) is True


def test_no_tool_calls_ends_the_graph():
    """没有 tool_calls ⇒ 结束，⛔ 不是"去审批"。"""
    from langchain_core.messages import AIMessage
    from langgraph.graph import END

    assert should_continue({"messages": [AIMessage(content="答案是 42")]}) == END


def test_unknown_tool_is_not_sensitive_by_default():
    """⛔ 白名单是**白名单** —— 没登记的工具**不**进审批。

    ⚠️ 这条是**故意的取舍**：默认"不敏感"意味着**新加的工具默认不过审批**。
       要它过，就得改 `SENSITIVE_TOOLS`（env）或改本文件。
       📌 若哪天裁定改成"默认敏感"，**改这一条 + 写明理由**，别悄悄改。
    """
    assert needs_approval(_calls("some_new_tool")) is False
```

- [x] **Step 2: 跑，确认失败**

```bash
python -m pytest api/test_approval_trigger.py -q
```
预期：`ImportError: cannot import name 'needs_approval'`

- [x] **Step 3: 实现（`api/agent_graph.py`）**

在 `search_tool = DuckDuckGoSearchRun()` **之前**加：

```python
# ==================== 人工审批的【触发条件】（B4 · 2026-09-30 改）====================
# 🔴 改前：**只要产生任意 `tool_calls` 就进审批** ⇒ 问一句"今天几号"也会停下来等人批。
#
# 现在：**只有【会对外产生副作用】的工具**才需要审批。
#   判据：「敏感」= **这个工具会把数据发到本机之外 / 产生不可撤销的外部效果**。
#   ⇒ `search_tool`（把问题原文发给 DuckDuckGo）**算**；
#      `calculator` / `date_today`（纯本地）**不算**。
#
# ⚠️ 从 env 读，逗号分隔。**默认值是 `search_tool`** —— 见 Task 0 的裁定。
SENSITIVE_TOOLS = frozenset(
    n.strip() for n in os.getenv("SENSITIVE_TOOLS", "search_tool").split(",") if n.strip()
)


def needs_approval(tool_calls: list) -> bool:
    """这一批工具调用里，**有没有任何一个**需要人工审批。

    ⚠️ 有任何一个敏感 ⇒ **整批都要批** —— ⛔ 不能"挑着执行敏感之外的"。
       理由：这批调用是**模型一次决定的**，拆开执行会让它看到的执行结果与它设想的不一致。
    """
    names = {tc.get("name") for tc in tool_calls or []}
    return bool(names & SENSITIVE_TOOLS)
```

把 `should_continue`（`:95`）改成：

```python
def should_continue(state: AgentState):
    """路由函数：没有工具调用 ⇒ 结束；有 **敏感** 工具调用 ⇒ 先审批；否则直接执行。

    ⚠️ 返回值有 **3 种**了（改前只有 2 种）—— 条件边的映射表要跟着改（见 `build_agent_graph`）。
    """
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    if not tool_calls:
        return END
    if needs_approval(tool_calls):
        return "approval"
    return "tools"
```

把条件边（`:130-137`）改成：

```python
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "approval": "approval",   # 敏感工具 ⇒ 先停，等人批
            "tools": "tools",         # 非敏感 ⇒ 直接执行（这是本次改动的关键）
            END: END,
        }
    )
```

- [x] **Step 4: 加"白名单不许为空"的启动校验**

在 `build_agent_graph()` **之前**加：

```python
def validate_approval_config():
    """启动时校验审批配置 —— ⛔ 不许让白名单【悄悄为空】。

    为什么必须有这条：白名单为空 ⇒ `needs_approval` 恒 False ⇒ **审批永不触发** ⇒
    **硬门 D 变成"有地基但从不启用"** —— 而**没有任何报错**，验收时才发现。
    ⇒ 让它**启动就报**，别等到验收。

    📌 同型前科：本仓 `embedding_client.py:10` 的模块级 `OpenAI(api_key=...)`
    —— key 为空会**炸掉整条 import 链**（`ROADMAP` 待办 **T1**）。
      那条是"**意外**为空就炸"；本条是"**该配的东西没配**就炸"，**方向相反、目的一样**。
    """
    if not SENSITIVE_TOOLS:
        raise EnvironmentError(
            "SENSITIVE_TOOLS 为空 ⇒ 人工审批永远不会触发，硬门 D 名存实亡。\n"
            "请在 .env 里配置至少一个会对外产生副作用的工具名，例如：\n"
            "    SENSITIVE_TOOLS=search_tool"
        )
```

然后在 `agent_graph = build_agent_graph()` 那行**之前**调用 `validate_approval_config()`。

- [x] **Step 5: 跑测试**

```bash
python -m pytest api/test_approval_trigger.py -q                        # → 5 passed
python -m pytest api/ -m "not integration and not needs_db" -q            # → 全绿
```

⚠️ **可能红**：`api/test_agent_repairs.py` 里有关于审批语义的用例（`:55-64` 那段注释就是它留下的）。
**红是预期的** —— 改的就是这个语义。**逐条看**：把"问日期会进审批"那类断言**改掉并写明新口径**，
⛔ **不要为了让测试过而回退实现**。

- [x] **Step 6: 补 `.env.example` + CHANGELOG + 提交**

```bash
# .env.example 加一行（带注释说明它是干什么的）：
#   SENSITIVE_TOOLS=search_tool    # 需要人工审批的工具（逗号分隔）
git add api/agent_graph.py api/test_approval_trigger.py .env.example CHANGELOG.md
git commit -m "feat(硬门D): B4 —— 审批触发改成敏感工具白名单，问日期不再进审批"
```

---

## Task 2 · **B5** · 待接管队列（数据 + 端点）· ✅ **已落地（2026-10-03）**

> ### ✅ 落地结果（2026-10-03）
>
> | 计划怎么写 | 实际怎么做 | 差异 |
> |---|---|---|
> | 6 个 Step | **6 个全做了** | — |
> | 4 条测试 | **7 条** | ➕ 3 条：**排序契约**（"卡得最久排最前"是 docstring 里写了却没人守的契约）· **启动警告的正反两条**（只测"设了会响"会误报） |
> | （计划没提接线守卫） | **➕ 新增 `api/test_pending_approvals_wiring.py`（6 条）** | 🔴 **接线是这个模块最可能静默坏掉的地方**（漏一处 ⇒ 队列**永远空**或**永远有假待办**，且**都不报错**）⇒ 按本仓 `*_wiring.py` 既有做法补上 |
> | （计划没提） | **➕ 那 6 条守卫逐条自证** | ⚠️ 它们是**写在实现之后**的（"tests-after"）⇒ **绿了不证明测的是对的东西**。⇒ 逐条把接线拆掉、确认对应测试**真会红**、再还原（脚本见 verdict：6/6 红了，还原后 6 passed） |
>
> **判据（可打印）**：
> ```bash
> venv/bin/python -m pytest api/test_pending_approvals.py api/test_pending_approvals_wiring.py -q
> # ⇒ 13 passed
> venv/bin/python -m pytest api/ -m "not integration and not needs_db" -q
> # ⇒ 237 passed, 3 skipped, 22 deselected, 0 failed   （本轮之前 224 ⇒ +13）
> ```
> **顺手改的口径**：路由 **28 → 29**（`ROADMAP` · `待办总表` · `后端补齐清单` 三处「28 个 agent 路由全部非流式」同步改）。


**Files:**
- Create: `api/pending_approvals.py` + `docs/specs/pending_approvals.md`（⛔ 新建模块必须同时建 spec）
- Create: `api/test_pending_approvals.py`（无 marker）
- Modify: `api/api_v1_agent.py`（新端点 + 在 `langgraph_chat` 里登记）

**Interfaces:**
- Produces: `register(thread_id, user_name, tool_calls) -> None` · `resolve(thread_id) -> None` · `list_pending() -> list[dict]`
- Produces: `GET /agent/pending` —— 返回 `[{"thread_id", "user_name", "since", "tool_calls"}]`

> ### 🔴 一个**必须写在 spec 里**的耦合
>
> **没法从 `MemorySaver` 里"列出所有卡住的会话"** —— 它只按 thread_id 取，**没有"列出全部"的 API**。
> ⇒ **必须自己建一张注册表**，在对话返回 `pending_approval` 时登记、在 `/agent/approve` 后注销。
>
> ⚠️ **而这张注册表放哪，必须与 checkpoint 后端一致**：
> · 默认 `MemorySaver`（`agent_graph.py:148`）⇒ 状态本来就在内存 ⇒ 注册表放内存**是一致的**
> · 但若设了 `AGENT_CHECKPOINT_BACKEND=sqlite` ⇒ **状态落盘了、注册表还在内存** ⇒
>   **重启后：图还在等审批，队列里却查不到** ⇒ 会话变孤儿
> ⇒ **本计划 v1 只支持内存**，并在 `pending_approvals.py` 顶部**写明这个限制** + 启动时若检测到 sqlite 后端就**警告**。

- [x] **Step 1: 写失败测试**

```python
# api/test_pending_approvals.py
"""待接管队列（B5）。⚠️ 不碰 DB / Redis —— 纯内存注册表。"""
import pending_approvals as pa


def test_register_then_list():
    pa.clear()                                   # 测试隔离
    pa.register("t1", "admin", [{"name": "search_tool", "args": {"q": "x"}}])
    rows = pa.list_pending()
    assert len(rows) == 1
    assert rows[0]["thread_id"] == "t1"
    assert rows[0]["user_name"] == "admin"
    assert "since" in rows[0]


def test_resolve_removes_it():
    """批完必须注销 —— 否则它会**永远留在队列里**，变成假待办。"""
    pa.clear()
    pa.register("t2", "admin", [])
    pa.resolve("t2")
    assert pa.list_pending() == []


def test_resolve_unknown_thread_is_a_noop():
    """重复注销 / 注销不存在的 ⇒ ⛔ **不许抛异常**（`/agent/approve` 会调到）。"""
    pa.clear()
    pa.resolve("never-registered")               # 不应抛


def test_register_twice_keeps_latest():
    """同一 thread 再次登记 ⇒ 更新，⛔ 不产生两条。"""
    pa.clear()
    pa.register("t3", "admin", [{"name": "a", "args": {}}])
    pa.register("t3", "admin", [{"name": "b", "args": {}}])
    rows = pa.list_pending()
    assert len(rows) == 1 and rows[0]["tool_calls"][0]["name"] == "b"
```

- [x] **Step 2: 跑，确认失败**（`ModuleNotFoundError: pending_approvals`）

- [x] **Step 3: 实现 `api/pending_approvals.py`**

```python
"""待接管会话的注册表（B5）。

⚠️ **为什么需要它**：`MemorySaver`（`agent_graph.py:148`）**没有"列出所有 thread"的 API**
   ⇒ **没法从 checkpoint 里反查"谁卡在审批"** ⇒ 只能自己记账。

🔴 **已知限制（v1）**：本表在**内存**里 ⇒ **进程重启即清空**。
   与默认的 `MemorySaver` **是一致的**（那个也在内存）。
   ⛔ **但若设了 `AGENT_CHECKPOINT_BACKEND=sqlite`**：图的状态落盘了，本表还在内存 ⇒
      **重启后图仍在等审批，而队列里查不到** ⇒ 会话变孤儿。启动时会给警告（见 `warn_if_backend_mismatch`）。
"""
import threading
import time

_lock = threading.Lock()
_pending: dict[str, dict] = {}


def register(thread_id: str, user_name: str, tool_calls: list) -> None:
    """登记一个卡在审批的会话。同一 thread 重复登记 ⇒ 覆盖。"""
    with _lock:
        _pending[thread_id] = {
            "thread_id": thread_id,
            "user_name": user_name,
            "tool_calls": list(tool_calls or []),
            "since": time.time(),
        }


def resolve(thread_id: str) -> None:
    """会话已不再等待审批 ⇒ 注销。⚠️ 注销不存在的**是正常的**（幂等），不抛异常。"""
    with _lock:
        _pending.pop(thread_id, None)


def list_pending() -> list[dict]:
    """按"卡住时间"升序 —— **卡得最久的排最前**（最该先处理）。"""
    with _lock:
        return sorted((dict(v) for v in _pending.values()), key=lambda r: r["since"])


def clear() -> None:
    """仅供测试隔离用。"""
    with _lock:
        _pending.clear()


def warn_if_backend_mismatch(logger=None) -> None:
    """checkpoint 落盘了、而本表在内存 ⇒ 重启后队列会丢。启动时提醒。"""
    import os
    if os.getenv("AGENT_CHECKPOINT_BACKEND") == "sqlite":
        msg = ("AGENT_CHECKPOINT_BACKEND=sqlite ⇒ 图状态会落盘，"
               "但待接管队列(pending_approvals)仍在内存 ⇒ 重启后队列会丢、会话变孤儿。"
               "见 docs/specs/pending_approvals.md")
        (logger.warning if logger else print)(msg)
```

- [x] **Step 4: 建 `docs/specs/pending_approvals.md`**（把上面那段「已知限制」原样搬进去 —— 它正是"看代码会误判"的那类）

- [x] **Step 5: 接端点（`api/api_v1_agent.py`）**

```python
from pending_approvals import list_pending, register, resolve


@router.get("/agent/pending")
async def list_pending_approvals(
    user_name: str = Depends(get_current_user_hybrid),
):
    """列出**当前等待人工接管**的会话（硬门 D 的入口）。

    判据（`通用/四硬门 §2` 的 L2 分水岭）：**能被前端当作一个独立可点的入口**。
    """
    rows = list_pending()
    return {"count": len(rows), "items": rows, "requested_by": user_name}
```

在 `langgraph_chat`（`:84`）里，拿到 `summary` **之后**：

```python
    if summary.get("status") == "pending_approval":
        register(thread_id, user_name, summary.get("pending_tool_calls") or [])
    else:
        resolve(thread_id)      # 本轮没卡住 ⇒ 清掉上一次的登记（否则会残留成假待办）
```

在 `approve_agent_action`（`:112`）里，**每条 return 之前**调 `resolve(thread_id)`。

- [x] **Step 6: 跑 + 提交**

---

## Task 3 · **B6** · 接管后续跑（含"改写后提交"）· ✅ **已落地（2026-10-03）**

> ### ✅ 落地结果（2026-10-03）
>
> | 计划怎么写 | 实际怎么做 | 差异 |
> |---|---|---|
> | 4 个 Step | **4 个全做了** | — |
> | 2 条测试 | **6 条** | ➕ 4 条：**`thread_id` 必须是请求里那个**（`None` 只保证"是续跑"，保证不了"续的是**这一条**"）· **改写必须是 `AIMessage`**（用 `HumanMessage` 会把"人给的结论"当**新输入**再答一遍）· **拒绝时不许写改写**（反面：只测"批准时会写"会漏掉这个）· **没停在审批点不许 `invoke`** |
> | 2 条里 1 条就该绿 | **确实绿了** | ⚠️ `invoke(None)` 与"早退不 invoke"这两条**改前就绿** ⇒ 它们是**回归守卫**，不是新功能（docstring 已写明） |
> | （计划没提自证） | **➕ 6/6 逐条变异自证** | 4 条新测试是**先红后绿**（真 TDD）；另 2 条是**钉现有行为**的守卫 ⇒ 逐条把接线改坏、确认**真会红**、再还原（脚本 `/tmp/prove-resume.py`：**6/6 RED**，还原后 **6 passed**） |
>
> **判据（可打印）**：
> ```bash
> venv/bin/python -m pytest api/test_approval_resume.py -q
> # ⇒ 6 passed
> venv/bin/python -m pytest api/ -m "not integration and not needs_db" -q
> # ⇒ 243 passed, 3 skipped, 22 deselected, 0 failed   （本轮之前 237 ⇒ +6，⛔ 无回归）
> ```
> ⚠️ **本 Task 只到"接线与语义"** —— **"上下文真的连续"没有端到端跑过**（要真 LLM + 真 `MemorySaver`，**联网花钱**）。
> ⇒ **硬门 D 的验收演示仍差这一步**，⛔ 别把"6 passed"读成"硬门 D 已验证"。


**Files:**
- Modify: `api/api_v1_agent.py`（`/agent/approve`）
- Test: `api/test_approval_resume.py`（**无 marker**，用假图）

**Interfaces:**
- Produces: `POST /agent/approve` 增加可选参数 **`edited_answer: str | None`**

- [x] **Step 1: 写失败测试**（用假图，⛔ 不真跑 LLM）

```python
# api/test_approval_resume.py
"""接管后续跑（B6）。

🔴 判据（`通用/四硬门 §3-D`）：**接管后会话【上下文连续】** —— 不是重开一轮。

⚠️ 用假图替掉 `agent_graph`：真图要调 LLM，**那会让这条测试变成"要联网、要花钱"**。
   本文件测的是【接线与语义】，不是模型质量。
"""
import api_v1_agent as m


class _FakeGraph:
    """记录被怎么调用，并能按剧本返回。"""
    def __init__(self):
        self.calls = []
        self._state = type("S", (), {"next": ("approval",)})()

    def get_state(self, config):
        return self._state

    def update_state(self, config, values=None):
        self.calls.append(("update_state", values))

    def invoke(self, arg, config):
        self.calls.append(("invoke", arg))
        # 续跑时传的是 None（= 从 checkpoint 继续），⛔ 不是新的 HumanMessage
        return {"messages": []}


def test_resume_invokes_with_none_not_a_new_message(monkeypatch):
    """🔴 **核心判据**：续跑必须 `invoke(None, config)`。

    ⛔ 若某天有人改成 `invoke({"messages": [HumanMessage(question)]}, …)`，
       那就是**重开一轮** —— 上下文断了，而**接口返回看着一切正常**。
    """
    fake = _FakeGraph()
    monkeypatch.setattr(m, "agent_graph", fake)
    m.approve_agent_action(thread_id="t1", approved=True, user_name="admin")
    assert ("invoke", None) in fake.calls, f"续跑没有用 None 续跑：{fake.calls}"


def test_edit_note_is_written_into_state(monkeypatch):
    """改写后提交：人工改的答案要进 state，**否则改了等于没改**。"""
    fake = _FakeGraph()
    monkeypatch.setattr(m, "agent_graph", fake)
    m.approve_agent_action(thread_id="t1", approved=True, user_name="admin",
                           edited_answer="人工改过的答案")
    values = [v for (k, v) in fake.calls if k == "update_state"]
    assert any("人工改过的答案" in str(v) for v in values), (
        f"edited_answer 没有被写进 state：{values}"
    )
```

- [x] **Step 2: 跑，确认失败**

```bash
python -m pytest api/test_approval_resume.py -q
```
预期：`TypeError: approve_agent_action() got an unexpected keyword argument 'edited_answer'`
（⚠️ 若它**直接通过**，说明 `invoke(None, …)` 那半条测的是现状 —— 那就把该断言留着当**回归守卫**，
并在 docstring 里写明"这是钉住现有正确行为的守卫，不是新功能"）

- [x] **Step 3: 给 `/agent/approve` 加 `edited_answer`**

```python
@router.post("/agent/approve")
async def approve_agent_action(
    thread_id: str,
    approved: bool,
    edited_answer: str = None,                 # 新增：人工改写后的答案（可选）
    user_name: str = Depends(get_current_user_hybrid),
):
    """
    人工审批：批准 / 拒绝 / **改写后提交**。

    🔴 续跑用的是 `agent_graph.invoke(None, config)` —— **`None` 表示"从 checkpoint 继续"**，
       ⛔ **不是**新开一轮。改成传新消息 = 上下文断裂，而接口返回**看着一样**。
       守卫见 `api/test_approval_resume.py`。

    `edited_answer`：人工把答案改过之后再放行。**不给就按原样续跑。**
    """
    from langchain_core.messages import AIMessage
    from pending_approvals import resolve

    config = {"configurable": {"thread_id": thread_id}}
    current_state = agent_graph.get_state(config)

    if current_state.next != ("approval",):
        resolve(thread_id)
        return {"status": "error", "message": "当前没有等待审批的任务"}

    if approved:
        if edited_answer is not None:
            # ⚠️ 用 update_state 把人工的改写**推进 messages**，而不是"跳过模型直接返回"
            #    —— 后者会让接下来的节点看不到这个改写。
            agent_graph.update_state(
                config, {"messages": [AIMessage(content=edited_answer)]}
            )
        result = agent_graph.invoke(None, config)      # ⭐ None = 续跑
    else:
        ...   # 拒绝分支：保持原样，只需在 return 前 resolve(thread_id)

    resolve(thread_id)
    return {"status": "approved" if approved else "rejected", ...}
```

- [x] **Step 4: 跑 + 提交**

```bash
python -m pytest api/test_approval_resume.py -q                       # → passed
python -m pytest api/ -m "not integration and not needs_db" -q          # → 全绿
git add api/api_v1_agent.py api/test_approval_resume.py
git commit -m "feat(硬门D): B6 —— 接管后续跑可带人工改写，并用测试钉住'从 checkpoint 续跑'"
```

---

# 🔵 实施计划 ③ · **流式与取消**（2026-09-30 立 · **2026-10-03 执行中**）

> **来源**：`后端补齐清单-待裁-20260929.md` 的 **B1 · B2 · B3**。
> **业务方已裁**：**B1 范围 = 只做 `/agent/langgraph_chat`**；**B2 验收 = 先以本机证据为准**。
> ⚠️ **排最后** —— B2 自标「**最容易假完成**」，且它的落点**依赖 B1 做完**。
>
> 📌 **进度**：**Task 4（`B1`）✅ 做完** · **Task 5（`B2`）⬜ 未做** · **Task 6（`B3`）⬜ 未做**

## Task 4 · **B1** · Agent 端 SSE（**范围：只 `/agent/langgraph_chat`**）· ✅ **2026-10-03 完成**

**Files:** Modify `api/api_v1_agent.py`（导 `StreamingResponse`、新增流式路由）· Test `api/test_agent_sse.py`

**Interfaces:** `POST /agent/langgraph_chat/stream` —— `media_type="text/event-stream"`

> ### ⛔ **一条硬约束（本次核查发现⑥）**
> **不能照抄 `api_v1_rag.py:655-662` 的写法** —— 那里 `.stream()` 是**同步迭代**，
> 在 async 生成器里 `for` **会阻塞事件循环**（`:662` 的 `await asyncio.sleep(0.01)` 是唯一让出点）。
> ⇒ Agent 端要用 **`astream`** 之类的异步迭代。

> ### 🔴🔴 **计划没覆盖的那一句（实际做的时候才发现它才是难点）**
> 计划把这件事当成"**服务端加条 SSE 路由**"。**真正决定成不成的在图的另一侧**：
> `astream(stream_mode="messages")` 要出**真 token**，**节点必须声明 `config: RunnableConfig`
> 并把它转发进模型的流式调用** —— 否则它只吐 **1 块**（整段），
> ⚠️ **而接口长得一模一样**（照样 `text/event-stream`、照样 `data:` 帧）⇒ **计划里那条"契约测试"根本判不出来**。
> ⇒ **两条改动**（本文件 + `api/agent_graph.py`），**裁定落 `DEC-050`**。

- [x] Step 1 写失败测试（**测"是不是真流式"，不是"有没有这个路由"**）：
  ⚠️ **计划的写法（TestClient 断言 `data:` ≥ 2）【不够】** —— 它**假流式也能过**。
  ✅ **实际做法**：把"真流式"拆成**可在离线测的机制**，钉在 `api/test_agent_sse.py`（12 例 · 纯离线 · 进 CI）：
  ① **块数**（`test_graph_streams_one_chunk_per_token` —— 数**块数**，⛔ 不看 header）
  ② **不重复**（`test_chunks_are_not_duplicated`）
  ③ **`tool_calls` 不丢**（`test_agent_decide_preserves_tool_calls`，B4 审批靠它）
  ④ **同步 `invoke()` 不能被弄坏**（`test_non_streaming_invoke_still_works`）
  ⑤ AST 判 `config` **真转发**了（⛔ 不是 grep 名字）
  ⑥ **空流不写 `None`**（`test_empty_stream_neither_writes_none_nor_returns_an_empty_answer`）
  ⑦ 端到端帧数 / 参数透传 / 停机登记 / 最终状态来源

- [x] Step 2 跑 → 失败 → Step 3 实现（**`astream` + `StreamingResponse`**）
- [x] Step 4 ⭐ **真服务的判据**（⛔ 别只用 TestClient）：

```bash
# 逐字节到达 = 真流式。看时间戳是否递增、连接是否保持不关闭
curl -N -s -X POST "http://127.0.0.1:8000/api/v1/agent/langgraph_chat/stream?question=你好&thread_id=t1" \
  -H "Authorization: Bearer $TOKEN" | while IFS= read -r line; do echo "$(date +%T.%3N)  $line"; done
```
  ⇒ 对照 `通用/四硬门 §3-A` 的 4 条判据（①逐字出现 ②`text/event-stream` **保持不关闭** ③**时间戳递增** ④日志里 token 计数**随 chunk 增长**）
  · ✅ **实测结果**：**29 个 token 帧，时间戳严格递增 `0.640s → 0.821s`**，随后 `status: answered` + `[DONE]`。
  · 🔴🔴 **这一步【真的抓到一个 bug】** —— 第二次调用（搜索类问题）返回 `status: "pending_approval"`，
    而图**其实已经跑完**。根因 = **结尾的 `summary` 是从"流过 `agent` 节点的块"攒出来的**，
    模型因工具返回"未找到工具"**重试**时节点进**多次** ⇒ 攒出了**上一轮的** `tool_calls`。
    ✅ **修法**：改从 **图的最终状态**取（`await agent_graph.aget_state(config)` ⇒ `summarize_agent_result`），
    与 `/agent/langgraph_chat` **同一套语义** ⇒ 再验：**216 个内容帧 + `status: answered` + `pending_tool_calls: null`**。
    📌 这条已经**进"看代码会误判"表**（本文件顶部）—— ⛔ 它是**计划里完全没写**的一步。
  · ⚠️ **本步的副作用（好的那种）**：真服务跑把**两个既有 bug**照了出来（`SENSITIVE_TOOLS` 默认值匹配不到
    任何真实工具 ⇒ **审批永不触发**；`tool_execute` 分派 `"search"` 而真名是 `duckduckgo_search` ⇒ **搜索永远失败**）
    ⇒ 详见 `docs/specs/agent_graph.md` 的 🟡 节。**两个都不是 `③` 引入的。**
- [x] Step 5 建/更 `docs/specs/api_v1_agent.md`（本文件）的状态行 → 提交
  · 同时更了 `docs/specs/agent_graph.md`（另一半）· 落 `DEC-050`

## Task 5 · **B2** · 服务端 cancel **传播到上游**（🔴🔴 自标「最容易假完成」）· ✅ **2026-10-03 已做**

**Files:** `api/api_v1_rag.py`（`stream_search`）+ `api/api_v1_agent.py`（流式端点）+ `api/metrics.py` ·
Test `api/test_cancel_propagation.py`（10 例 · 纯离线 · 进 CI）

**计划要补三件**：① 检测客户端断开（`request.is_disconnected()`）② **主动关上游 HTTP 流** ③ **`finally` 兜底**

> ### ⚠️ 执行下来：**①不用补 · ②③照做 · 而计划里的验收判据【落空了】**
>
> | 计划 | 实际 |
> |---|---|
> | ① `is_disconnected()` | ⛔ **不用写** —— uvicorn 报 `spec_version 2.3` ⇒ **Starlette 已经替我们监听 `http.disconnect` 并取消生成器**。真正的缺口**只有②**（`DEC-052` §①不用补） |
> | ② 关上游 | ✅ 上游改 `astream`（同步 `for` 会**阻塞事件循环**，取消得等下一块）+ `finally: await stream.aclose()` |
> | ③ `finally` 兜底 | ✅ 且**必须**放 `finally` —— Starlette 有**两条**关闭路径（2.3 抛 `CancelledError` / 2.4 抛 **`GeneratorExit`**），后者**不是** `CancelledError` 子类 ⇒ 只写 `except` 会**静默不记** |
> | 🔴 判据 ③「**token 计数停止增长**」 | ⛔ **该计数在流式路径上不存在**（`grep -ci token api/metrics.py` = 0；PG 记账**只在生成结束后整笔写**）⇒ **判据无法证伪 = 任何实现都能通过**。<br>✅ 换成：① 日志有 `[cancel]` ② `stream_cancelled_total{endpoint}` **+1** ③ `outcome == "cancelled"`（**循环没跑完** ⇒ 比"计数涨了"更接近"上游真停了"） |

> ### ✅ 验收口径（**业务方 2026-09-30 已裁：先以本机证据为准**）
> ⚠️ **已知代价仍然成立**：**证明不了"上游计费真的停"** —— 本机没有 DashScope 侧账单。
> ⇒ **接受它**；上云后（阶段⑦/⑧）若有机会再补真链路，但**不作为本轮验收前提**。
> ⛔ 因此本轮**不许**把"我们关了流"说成"账单停了"（`DEC-052` §遗留·2）。

- [x] Step 1 写测试 —— ⛔ **⾏不通**：计划里的 `test_token_counter_stops_after_cancel` **写不出来**
      （被测对象不存在，见上表）。改写为 `api/test_cancel_propagation.py`（10 例）——
      **钉在 ASGI 层**：把 `StreamingResponse` 当 ASGI app 跑（`spec_version="2.3"`，与 uvicorn 实测一致），
      `receive` 在第 N 帧后回 `http.disconnect` ⇒ 与真服务器**走同一段取消代码**
- [x] Step 2 跑 → **红**（⚠️ 第一版假上游写成 `async def` + `yield`，**假绿** —— `asyncio.run()` 收尾的
      `shutdown_asyncgens()` 会替我们把它关掉 ⇒ 改成**手写迭代器**，`closed` 为真**只能**是我们调的 `aclose()`）
- [x] Step 3 实现（⚠️ `finally` 是**主路**不是兜底 —— 三条出口都要关流）
- [x] Step 4 ⭐ **真服务（本机）**：`curl --max-time` 切断，两条端点各验一遍
      —— ✅ 计数 1.0 → **2.0**（rag）/ **→ 1.0**（agent）+ 各有 `[cancel]` 日志行
      ⚠️ **两个坑记在 `DEC-052`**：中间件时长**不是**生成时长 · 本机**有语义缓存**（换问句才能测）
- [x] Step 5 提交，并在 `docs/specs/api_v1_rag.md` 里把「不关上游 HTTP 流」那条**划掉**（本文件同改）

## Task 6 · **B3** · ✅ **2026-10-03 已做**（「先核」核出了别的东西）

**核的结果（判据两条都没过，①的根因比判据假设的大一圈）：**

| 判据 | 核出来什么 |
|---|---|
| **①** cancel 后已产生的 token **有记账** | ❌ **落空，且不是"取消时没记"** —— `grep -c record_usage api/api_v1_rag.py` ⇒ **0**、`api/rag_pipeline.py` ⇒ **0** ⇒ **RAG 侧四条调 LLM 的路径从来不记账**（成功也不记）。真库佐证：非 embedding 行**全库只有 6 行**，全是 2026-09-20 的 agent graph 运行 |
| **②** 半截答案处理方式**明确** | ⚠️ 现状是**丢**，但**不是决定、是碰巧** —— `append_chat_history` 写在循环之后，取消在它之前 `raise`；⚠️ **用户那句提问跟着一起丢** |

⚠️ **还有一条技术上绕不过去的**：取消瞬间的 token 数**协议上拿不到** ——
`api/llm_factory.py` 没开 `stream_usage`，usage 只在**最后一帧**回来，而我们提前 `aclose()` ⇒
那一帧**永远不会到**。⇒ 硬补只能估算 = **往账本写假数**，比空着更坏。

**决策（`DEC-053`）**：**存**，不是丢 ——
① 作者原意就是存（`api_v1_rag.py:667` 注释写着"**使它支持历史补偿**"）；
② 存的形态 = 提问 + 半截 + `INTERRUPTED_SUFFIX` 标记（**成对写**，标记**必须**有，否则下一轮 prompt 会把断话当说完）；
③ 落点是 **`finally`**（⛔ 不是 `except CancelledError` —— 2.4 分支抛 `GeneratorExit`，同 `DEC-052`）；
④ 一块都没生成 ⇒ **什么都不写**。

**Agent 端这边【不用改】** —— 它的"半路状态"由 langgraph 的 checkpointer（`MemorySaver`，
`api/agent_graph.py:250`）持有，取消时**已经落在里面**了；RAG 端什么都没有 ⇒ 两端本来就不对称。
⚠️ **`MemorySaver` 是【进程内存】** ⇒ 与我们自己的 `pending_approvals` 同一个限制：**重启即空**。

- [x] Step 1~3 测试先红后绿（`api/test_cancel_propagation.py` 10 → **13 例**）
      —— ⚠️ 第三条（"一块都没生成就不写"）**红不出来**（改动前它本来就过）⇒ 它是**反面守卫**，防"修过头"
- [x] Step 4 ⛔ **没起 Docker 真服务**（用户本轮手动关了 `rag-api`）—— ⚠️ **这次是能省的**：
      本任务的判据落在**进程内**，而测试走的是**真 ASGI 断开**（与 `B2` 同一段取消代码），
      `B2` 那轮必须真服务是因为要证「Prometheus 计数在真 uvicorn 下也涨」，这一轮没有同类的"跨进程"观测对象。
      ⚠️ **仍未端到端验的是**：「**下一轮 prompt 真的读到了那半截**」——
      那要真 LLM + 真 Redis 续问一轮（本机 `MemorySaver`/Redis 都在，**是可做的，只是本轮没做**）

- [x] Step 5 写进 `DEC-053` + `docs/specs/api_v1_rag.md`（本文件同改）
