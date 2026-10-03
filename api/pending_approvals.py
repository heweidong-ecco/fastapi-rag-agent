"""待接管会话的注册表（B5 · 硬门 D）。

⚠️ **为什么需要它**：`MemorySaver`（`agent_graph.py` 里 `build_agent_graph()` 的末行）
   **没有"列出所有 thread"的 API** —— 它只按 `thread_id` 取。
   ⇒ **没法从 checkpoint 反查"谁卡在审批"** ⇒ 只能自己记账。

🔴 **已知限制（v1）**：本表在**内存**里 ⇒ **进程重启即清空**。
   与**默认的** `MemorySaver` **是一致的**（那个也在内存）⇒ 两边一起丢，不会对不上。

   ⛔ **但若设了 `AGENT_CHECKPOINT_BACKEND=sqlite`**：**图的状态落盘了、本表还在内存** ⇒
      **重启后图仍在等审批，而队列里查不到** ⇒ 会话变孤儿（谁也找不到它，它自己也走不下去）。
      ⚠️ **这个组合不会自己报错** —— 要等人重启后去队列里找才发现。
      ⇒ 启动时由 `warn_if_backend_mismatch()` 给警告（唯一的防线）。

📄 计划 / 裁定 ⇒ `docs/specs/api_v1_agent.md` 的「实施计划 ② · Task 2」·
   模块 spec ⇒ `docs/specs/pending_approvals.md` · 判据 ⇒ `api/test_pending_approvals.py`
"""
import threading
import time

# ⚠️ `threading.Lock` 不是装饰 —— 端点连 `agent_graph` 都在多线程下跑，
#    而 register / resolve / list_pending 会被不同请求并发调到。
_lock = threading.Lock()
_pending: dict[str, dict] = {}


def register(thread_id: str, user_name: str, tool_calls: list) -> None:
    """登记一个卡在审批的会话。同一 thread 重复登记 ⇒ **覆盖**（⛔ 不产生两条）。"""
    with _lock:
        _pending[thread_id] = {
            "thread_id": thread_id,
            "user_name": user_name,
            "tool_calls": list(tool_calls or []),
            "since": time.time(),
        }


def resolve(thread_id: str) -> None:
    """会话已不再等待审批 ⇒ 注销。

    ⚠️ **注销不存在的【是正常的】**（重复点批准 / 线程从没卡住过）⇒ **幂等，不抛异常**。
       `/agent/approve` 会调到它，而那条路**本来就会遇到"没有待审批任务"的情况**。
    """
    with _lock:
        _pending.pop(thread_id, None)


def list_pending() -> list[dict]:
    """列出全部待接管会话，**按"卡住时间"升序** —— **卡得最久的排最前**（最该先处理）。

    ⚠️ 返回的是**浅拷贝**（`dict(v)`）⇒ 调用方改返回值的**顶层字段**不会影响注册表；
       ⛔ 但 `tool_calls` 那个 list 是**共享**的（浅拷贝）—— 别去改它。
    """
    with _lock:
        return sorted((dict(v) for v in _pending.values()), key=lambda r: r["since"])


def clear() -> None:
    """清空。⚠️ **仅供测试隔离用** —— 生产代码里没有调用点（⛔ 别拿它当"重置"接口）。"""
    with _lock:
        _pending.clear()


def warn_if_backend_mismatch(logger=None) -> None:
    """checkpoint 落盘了、而本表在内存 ⇒ 重启后队列会丢。**启动时提醒。**

    ⚠️ 只在 `AGENT_CHECKPOINT_BACKEND=sqlite` 时出声 —— 默认的内存后端**两边一致**，
       那时**必须安静**（恒响的警告 = 把真警告淹掉）。
    """
    import os
    if os.getenv("AGENT_CHECKPOINT_BACKEND") == "sqlite":
        msg = ("AGENT_CHECKPOINT_BACKEND=sqlite ⇒ 图状态会落盘，"
               "但待接管队列(pending_approvals)仍在内存 ⇒ 重启后队列会丢、会话变孤儿。"
               "见 docs/specs/pending_approvals.md")
        (logger.warning if logger else print)(msg)
