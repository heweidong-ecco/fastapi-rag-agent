# `api/pending_approvals.py`

| 项 | 内容 |
|---|---|
| **状态** | 🆕 **新建（2026-10-03 · `②` Task 2 · `B5`）** —— 待接管队列（硬门 D 的"数据"那一半） |
| **对外提供** | 函数 `register` / `resolve` / `list_pending` / `clear` / `warn_if_backend_mismatch`；<br>经路由 **`GET /agent/pending`** 露出 |
| **谁在用** | `api_v1_agent.py` —— `langgraph_chat`（登记/注销）· `approve_agent_action`（注销）· `list_pending_approvals` 端点 |

## ✅ 做了什么

- **一张内存注册表**：`{thread_id → {thread_id, user_name, tool_calls, since}}`，`threading.Lock` 保护
- `register`（同一 thread **覆盖**）· `resolve`（**幂等**，注销不存在的**是正常的**）· `list_pending`（**卡得最久的排最前**）
- `warn_if_backend_mismatch()` —— 启动警告（见下）

## 🟡 做到哪 / 缺什么

- ⚠️ **只在内存** ⇒ **进程重启即清空**（v1 有意如此，见下）
- ⬜ **没有分页 / 过滤** —— `list_pending()` 一次返回全部。⚠️ 队列长起来会一次性打给调用方
- ⬜ **没有"超时自动清理"** —— 登记后没人处理，它会**一直留在队列里**（在进程活着的前提下）
- ⬜ **`B6`（接管后续跑）未做** ⇒ 本模块只管"**谁在等**"，不管"**批了之后怎么继续**"
- ✅ **有测试**：`api/test_pending_approvals.py`（7 条 · **纯离线** ⇒ 进 CI）

## ⚠️ 看代码会误判的地方 ⭐

| 看代码会以为 | 实际 |
|---|---|
| 🔴 **「`MemorySaver` 里存着全部会话，反查一下就知道谁卡住了」** | ⛔ **不能** —— `MemorySaver` **只按 `thread_id` 取，没有"列出全部"的 API**。**这正是本模块存在的唯一理由**。⚠️ 别试图绕过它去读 checkpoint |
| 🔴 **「重启后队列还在」** | ⛔ **不在** —— 它是**进程内存**，重启即空。⚠️ **与默认的 `MemorySaver` 一致**（那个也在内存）⇒ 两边一起丢，**不会对不上** |
| 🔴 **「设了 `AGENT_CHECKPOINT_BACKEND=sqlite` 也没事」** | ⚠️ **有事** —— 那时**图落盘、队列不落盘** ⇒ **重启后图仍在等审批、队列里查不到** ⇒ **会话变孤儿**（谁也找不到它，它自己也走不下去）。<br>⚠️ **这个组合不会自己报错** ⇒ **唯一防线是启动时那条警告**（`warn_if_backend_mismatch`）。<br>⇒ **本模块 v1 只支持内存后端**，⛔ 别在没改这个的前提下开 sqlite |
| ⚠️ **「`resolve` 注销一个不存在的 thread 会报错」** | ⛔ **不报** —— **幂等**。`/agent/approve` 会调到它，而那条路**本来就会遇到"没有待审批任务"**（那时要求它不抛） |
| ⚠️ **「`list_pending` 随便什么顺序都行」** | ⛔ **有契约**：**按 `since` 升序 = 卡得最久的排最前**（最该先处理）。⚠️ 排错了**不会报错**，只会让人**从最不紧急的那条开始处理** |
| ⚠️ **「返回的 dict 可以随便改」** | ⚠️ **浅拷贝** —— 改**顶层字段**不影响注册表，但 **`tool_calls` 那个 list 是共享的**，⛔ 别去改 |
| ⚠️ **「`clear()` 是个重置接口」** | ⛔ **不是** —— **仅供测试隔离**。**生产代码里零调用点** |

## 关联

`B5`（`后端补齐清单`）· `docs/specs/api_v1_agent.md`（**计划 ② · Task 2** —— 逐 Step 真代码）
· `docs/specs/agent_graph.md`（`interrupt_before=["approval"]` 那一侧 —— **本模块记的是"谁停了"，它管的是"为什么停"**）
· `ROADMAP.md`（硬门 D 那一行）· `DEC-048`（审批触发条件的决策前提 —— **决定谁会被登记进来**）
