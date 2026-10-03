"""`/agent/memory_chat` 的**审批门** + `/agent/approve` 的**按图路由**（`DEC-056` 丙段）。

🔴 **两条现状**：
   1. `agent_checkpointer.py`（`/agent/memory_chat` 走它）**没有审批门**
      —— 无 `interrupt_before` / 无 `SENSITIVE_TOOLS`（`DEC-051` §遗留·2）⇒
      **同一个仓里，一条路停下等人批，另一条直接执行。**
   2. `/agent/approve` 把 **`agent_graph` 写死**了 ⇒ 光给 ① 加门而不改它，
      **会话会停在审批点、永远没人能放行**（比不加固还糟）。
   ⇒ 业务方 2026-10-03 裁：**按登记表里的图路由**（一个入口，两张图都认）。

📌 判据（可打印）：
    `venv/bin/python -m pytest api/test_memory_chat_approval.py -q -p no:warnings`
"""
import asyncio
import types

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import agent_checkpointer as ac
import agent_graph as ag
import api_v1_agent as m
import pending_approvals as pa
from session_key import session_key

THREAD = "default"


# ==================== ① 门真的会把图停住 ====================

class _StubTool:
    """⛔ 只在**门没生效**（RED）时才跑得到 —— 挡住真联网，让红灯是"断言失败"而不是"卡住"."""

    def invoke(self, args):
        return "stub"


class _ScriptedLLM:
    """第一次返回**敏感工具调用**，之后返回普通答案。

    ⚠️ 必须有"之后"：门**没生效**时，假模型每次都回 tool_calls ⇒
       `agent → tools → agent …` **转到递归上限**，红灯变成 `GraphRecursionError`
       （吵、且看不出是哪条断言坏的）。
    """

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "web_search", "args": {"query": "x"}, "id": "c1"},
            ])
        return AIMessage(content="done")


def test_memory_chat_graph_stops_at_approval_for_sensitive_tools(monkeypatch):
    """⭐ 丙段的门 —— 含**敏感**工具时，图必须**停在审批点**（`get_state().next == ("approval",)`）。

    ⚠️ 这是**端到端**的：真编图、真走 `should_continue`，只有 LLM 是假的（不联网）。
    """
    monkeypatch.setattr(ac, "llm_with_tools", _ScriptedLLM())
    monkeypatch.setattr(ac, "TOOLS_BY_NAME", {"web_search": _StubTool()})

    g = ac.build_checkpointer_agent("memory")
    cfg = {"configurable": {"thread_id": "t-gate"}}
    g.invoke({"messages": [HumanMessage(content="q")]}, config=cfg)

    assert g.get_state(cfg).next == ("approval",), (
        "敏感工具没能把图停在审批点 —— 说明 `checkpointer_agent` 上**没有** "
        "`interrupt_before=['approval']`（`DEC-051` §遗留·2 / `DEC-056` 丙段）"
    )


def test_gate_shares_one_whitelist_with_agent_graph():
    """🔴 **白名单只能有一份** —— ⛔ 别在 `agent_checkpointer` 里再抄一遍 `SENSITIVE_TOOLS`。

    ⚠️ 抄一份就是 `DEC-051` 记的那个病根：同一个判断两处实现，**改了一边另一边不知道**，
    而两处不一致时**不报错**（审批静默地永不触发 / 静默地对错的工具触发）。
    """
    assert ac.SENSITIVE_TOOLS is ag.SENSITIVE_TOOLS, (
        "`agent_checkpointer` 的敏感名单不是 `agent_graph` 那一份 ⇒ 又变成两处口径了"
    )


# ==================== ② 停住之后，队列里要记【是哪张图】 ====================

def test_memory_chat_registers_pending_with_graph_name(monkeypatch):
    """停在审批点 ⇒ 登记时**必须写明图名**，否则 `/agent/approve` 不知道该续跑哪张。"""
    pending_result = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "web_search", "args": {"query": "x"}, "id": "c1"},
    ])]}
    fake = types.SimpleNamespace(invoke=lambda state, config=None: pending_result)
    monkeypatch.setattr(m, "checkpointer_agent", fake)
    monkeypatch.setattr(m, "check_session_token_budget", lambda u, t, **kw: (True, ""))
    monkeypatch.setattr(m, "circuit", lambda k: (True, ""))
    pa.clear()

    out = asyncio.run(m.memory_chat(question="q", thread_id=THREAD, user_name="alice"))

    assert out["status"] == "pending_approval", (
        "`memory_chat` 必须**告诉调用方**它在等审批（⛔ 别返回 200 + 空答案）"
    )
    rows = pa.list_pending()
    assert len(rows) == 1
    assert rows[0]["graph"] == "checkpointer_agent", (
        f"登记表里没写明是 `/agent/memory_chat` 那张图（实际 {rows[0].get('graph')!r}）"
    )
    assert rows[0]["raw_thread_id"] == THREAD
    assert rows[0]["thread_id"] == session_key("alice", THREAD)


# ==================== ③ approve 必须按【登记的图】路由 ====================

class _FakeGraph:
    def __init__(self, next_=("approval",)):
        self.trace = []
        self._next = next_

    def get_state(self, config):
        self.trace.append(("get_state", config))
        return types.SimpleNamespace(next=self._next, values={})

    def update_state(self, config, values=None):
        self.trace.append(("update_state", config))
        return config

    def invoke(self, state, config=None):
        self.trace.append(("invoke", config))
        return {"messages": [AIMessage(content="done")]}


def _approve(**kw):
    kw.setdefault("thread_id", THREAD)
    kw.setdefault("approved", True)
    kw.setdefault("edited_answer", None)
    kw.setdefault("user_name", "alice")
    return asyncio.run(m.approve_agent_action(**kw))


def test_approve_routes_to_checkpointer_graph(monkeypatch):
    """⭐ `memory_chat` 卡住的会话，`/agent/approve` 必须去找 **`checkpointer_agent`**。

    ⚠️ 改动前：approve 把 `agent_graph` 写死 ⇒ 它会去问**另一张图**"你有没有停在审批点" ⇒
       答"没有" ⇒ 这个会话**永远放行不了**（比不加门还糟：门关了却没有钥匙）。
    """
    pa.clear()
    pa.register(session_key("alice", THREAD), "alice", [{"name": "web_search", "args": {}}],
                raw_thread_id=THREAD, graph="checkpointer_agent")
    ckpt = _FakeGraph()
    plain = _FakeGraph()
    monkeypatch.setattr(m, "checkpointer_agent", ckpt)
    monkeypatch.setattr(m, "agent_graph", plain)

    out = _approve(user_name="alice")

    assert out["status"] == "approved"
    assert ckpt.trace, "必须续跑 `checkpointer_agent`"
    assert plain.trace == [], "⛔ 不许去碰 `agent_graph` —— 那不是这个会话的图"


def test_approve_routes_to_agent_graph_by_default(monkeypatch):
    """回归：`/agent/langgraph_chat` 那条路（`graph` 默认值）仍走 `agent_graph`。"""
    pa.clear()
    pa.register(session_key("alice", THREAD), "alice", [{"name": "web_search", "args": {}}],
                raw_thread_id=THREAD)
    ckpt = _FakeGraph()
    plain = _FakeGraph()
    monkeypatch.setattr(m, "checkpointer_agent", ckpt)
    monkeypatch.setattr(m, "agent_graph", plain)

    assert _approve(user_name="alice")["status"] == "approved"
    assert plain.trace and ckpt.trace == []


def test_approve_refuses_unknown_graph_name(monkeypatch):
    """⛔ 图名不认识 ⇒ **如实报错**，别"猜一个" —— 猜错就是往别人会话上写状态。"""
    pa.clear()
    pa.register(session_key("alice", THREAD), "alice", [], raw_thread_id=THREAD, graph="no_such_graph")
    plain = _FakeGraph()
    monkeypatch.setattr(m, "agent_graph", plain)

    out = _approve(user_name="alice")

    assert out["status"] == "error"
    assert plain.trace == []
