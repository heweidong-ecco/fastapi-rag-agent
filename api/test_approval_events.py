"""审批留痕 `api/approval_audit.py` —— **离线可跑的那一半**（假 pg，⛔ 不连库）。

🔴 本文件钉的第一件事：**`owner` 与 `actor` 是两个身份**。
   admin 接管 alice 的会话时，`owner="alice"` 而 `actor="admin"` ——
   把两者合成一个字段，**留痕当场变成假话，而且不报错**。
   ⇒ 本用例传**两个不同的值**，断言写进去的**也是两个不同的值**。
   （反证检验：把它取反成"两者相同"，`test_records_owner_and_actor_separately` 立刻红。）

📌 判据（可打印）：`venv/bin/python -m pytest api/test_approval_events.py -q -p no:warnings`
"""
import db
import approval_audit as aa


class _FakeCursor:
    def __init__(self, log):
        self.log = log
        self._rows = []
        self.rows_to_return = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))
        if "SELECT" in sql.upper():
            self._rows = self.rows_to_return

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows=None):
        self.log = []
        self.rows_to_return = rows or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        cur = _FakeCursor(self.log)
        cur.rows_to_return = self.rows_to_return
        return cur

    def commit(self):
        self.log.append(("COMMIT", None))


def _fake_db(monkeypatch, rows=None):
    conn = _FakeConn(rows)
    monkeypatch.setattr(db, "get_db", lambda: conn)
    return conn


def _insert_of(conn):
    """取出那次 INSERT 的 (sql, params)；⛔ 不靠"日志里有几行"。"""
    for sql, params in conn.log:
        if sql.upper().startswith("INSERT"):
            return sql, params
    raise AssertionError(f"没有 INSERT —— 实际日志：{[s for s, _ in conn.log]}")


def _select_of(conn):
    for sql, params in conn.log:
        if sql.upper().startswith("SELECT"):
            return sql, params
    raise AssertionError(f"没有 SELECT —— 实际日志：{[s for s, _ in conn.log]}")


# ==================== ① 核心：两个身份 ⛔ 不是一个 ====================

def test_records_owner_and_actor_separately(monkeypatch):
    """⭐ 本文件最重要的一条：**owner 是会话的，actor 是动手的**。"""
    conn = _fake_db(monkeypatch)

    aa.record_decision(owner="alice", actor="admin", decision="approved",
                       edited=False, raw_thread_id="default", graph="agent_graph",
                       rounds=2, reason="web_search")

    _, params = _insert_of(conn)
    assert "alice" in params and "admin" in params, f"两个身份没都写进去：{params}"
    assert params.index("alice") != params.index("admin"), (
        "owner 与 actor 被写成了同一个值 —— admin 接管 alice 的会话时它们【必须】不同"
    )


def test_creates_table_lazily(monkeypatch):
    """表是**惰性建的**（照 `budget_intercepts` 抄）—— 跑一次就得看到 `CREATE TABLE IF NOT EXISTS`。

    ⚠️ 没有它，全新库上第一条裁决会 `UndefinedTable` —— 而那是**在审批路径上**炸的。
    """
    conn = _fake_db(monkeypatch)

    aa.record_decision(owner="a", actor="a", decision="rejected", edited=False)

    sqls = [s.upper() for s, _ in conn.log]
    assert any("CREATE TABLE IF NOT EXISTS APPROVAL_EVENTS" in s for s in sqls), (
        f"没有惰性建表 —— 实际：{sqls}"
    )


# ==================== ② fail-open：留痕坏了 ⛔ 不许把审批带崩 ====================

def test_is_fail_open_when_db_unavailable(monkeypatch):
    """🔴 写留痕失败 ⇒ **不抛**。造一条审批记录 ⛔ 不该让「批准」这个动作 500。"""
    def _boom(*_a, **_kw):
        raise RuntimeError("模拟 DB 不可用")

    monkeypatch.setattr(db, "get_db", _boom)

    aa.record_decision(owner="a", actor="b", decision="approved", edited=False)   # 不应抛


def test_read_is_fail_open_too(monkeypatch):
    """读那条路同样 fail-open（页面上少一段历史 ⛔ 好过整页 500）。"""
    def _boom(*_a, **_kw):
        raise RuntimeError("模拟 DB 不可用")

    monkeypatch.setattr(db, "get_db", _boom)

    assert aa.list_decisions(owner="a") == []


# ==================== ③ 读：owner 收窄（⛔ 不许悄悄全量） ====================

def test_list_narrows_by_owner(monkeypatch):
    conn = _fake_db(monkeypatch)

    aa.list_decisions(owner="alice")

    sql, params = _select_of(conn)
    assert "WHERE" in sql.upper() and "OWNER" in sql.upper(), f"没有按 owner 收窄：{sql}"
    assert params == ("alice", 50), (
        f"参数应是 (owner, limit)，实际 {params} —— ⚠️ owner 没进 SQL 就是**查了所有人**"
    )


def test_list_owner_none_means_all(monkeypatch):
    """`owner=None` ⇒ **全量**（admin 那条路）。⚠️ 它必须**显式传** —— 见模块签名。"""
    conn = _fake_db(monkeypatch)

    aa.list_decisions(owner=None)

    sql, params = _select_of(conn)
    assert "OWNER = " not in sql.upper(), f"owner=None 却仍带了 owner 过滤：{sql}"
    assert params == (50,), f"owner=None 时参数里不该有 owner，实际 {params}"


def test_list_returns_rows_as_dicts(monkeypatch):
    """返回的是 **dict 列表**（页面直接塞 JSON）—— 名字对得上 DDL 里的列。"""
    _fake_db(monkeypatch, rows=[("alice", "admin", "approved", False, 2, "web_search")])

    got = aa.list_decisions(owner="alice")

    assert got == [{"owner": "alice", "actor": "admin", "decision": "approved",
                    "edited": False, "rounds": 2, "reason": "web_search"}]


def test_list_forces_owner_to_be_explicit():
    """🔴 `owner` 是**必填关键字参数** —— 忘了传 ⇒ 当场 `TypeError`。

    ⚠️ 这条守的是「**静默全量**」那个漏洞：给 `owner` 一个 `None` 默认值，
       "我忘了传" 与 "我要查所有人" 就再也分不出来了（`DEC-055` 口径）。
    """
    import pytest
    with pytest.raises(TypeError):
        aa.list_decisions(limit=10)


# ==================== ④ 「为什么」的摘要 ====================

def test_summarize_tool_calls():
    assert aa.summarize_tool_calls([{"name": "web_search"}]) == "web_search"
    assert aa.summarize_tool_calls(
        [{"name": "web_search"}, {"name": "web_search"}, {"name": "python_repl"}]
    ) == "web_search×2、python_repl"
    assert aa.summarize_tool_calls([]) == "(无工具调用)"
    assert aa.summarize_tool_calls(None) == "(无工具调用)"


# ==================== ⑤ 端点层：本人默认 · admin 全量 ====================

import asyncio
import api_v1_agent as m


def _history(monkeypatch, user_name, limit=50):
    """直接调端点函数（⛔ 不经过 TestClient ⇒ 不触发 lifespan ⇒ 不需要库）。"""
    seen = {}

    def _fake_list(*, owner, limit):
        seen["owner"] = owner
        seen["limit"] = limit          # ⚠️ 施工单这份假货漏了它，而它自己的用例要断言它
        return []

    monkeypatch.setattr(m, "list_decisions", _fake_list)
    out = asyncio.run(m.agent_approval_history(limit=limit, user_name=user_name))
    return out, seen


def test_history_narrows_to_self(monkeypatch):
    out, seen = _history(monkeypatch, "alice")
    assert seen["owner"] == "alice", f"普通用户必须只看自己的，实际查了 {seen['owner']!r}"
    assert out == {"events": [], "count": 0, "requested_by": "alice"}


def test_history_admin_gets_all(monkeypatch):
    """admin ⇒ `owner=None`（全量）。⚠️ 这个 `None` 必须**显式传**，见模块签名。"""
    _, seen = _history(monkeypatch, "admin")
    assert seen["owner"] is None, "admin 应当查全量"


def test_history_passes_limit_through(monkeypatch):
    """`limit` ⛔ 别收下不用（签名看着对、行为是死的 —— 本仓栽过）。"""
    _, seen = _history(monkeypatch, "alice", limit=7)
    assert seen["limit"] == 7
