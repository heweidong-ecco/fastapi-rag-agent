"""契约 D：`api_keys.is_active` 真的参与校验（`DEC-085`）。

🔴 本文件的**核心手法**：把 `verify_api_key` **真发给库的那句 SQL** 抓下来，
   把 `%s` 换成 `?` 丢进 `sqlite3` **原地执行** ——
   ⇒ 被测的是**产品代码产出的谓词本身**，⛔ 不是我在测试里照抄一份
     （照抄只能测"我抄对没有"，产品代码改成什么都照样绿）。

🔴 **为什么要防 NULL**：迁移 `828721f77ef2` 建列时写的是
   `sa.Column('is_active', sa.Integer(), server_default='1', nullable=True)`
   —— **`nullable=True`** ⇒ 真库里**可能**有 `is_active IS NULL` 的老行。
   写成 `WHERE is_active = 1`，那些行会被**静默排除** ⇒ **老 key 集体失效**，
   而用户只看到一句"凭据无效"，**查不到点上**（同 `deps.py` 剥空白那条教训）。
   ⚠️ "现网有没有 NULL 行"**没验过**（当时库没起）—— **正因为没验过**，写法必须防 NULL。
"""
import datetime
import sqlite3

import pytest

import auth


class _FakeCursor:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params

    def fetchone(self):
        # 未过期的一行 —— 走到 SQL 之后那几步不该成为本文件的变量
        return ("alice", datetime.datetime.now() + datetime.timedelta(days=1))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def captured_sql(monkeypatch):
    """跑一次真的 `verify_api_key`，把它发给库的那句 SQL 抓出来。

    ⚠️ 打的是 `auth.get_db` —— `api/auth.py:7` 用的是 `from db import get_db`
       （**直接绑定**）⇒ 打 `db.get_db` 是**空操作**，改源模块 `auth` 自己才有效。
    """
    cur = _FakeCursor()
    monkeypatch.setattr(auth, "get_db", lambda: _FakeConn(cur))
    monkeypatch.setattr(auth, "hash_api_key", lambda k: "hash-" + k)
    assert auth.verify_api_key("sk-x") == "alice"      # 顺带：正常路径仍要通
    return cur.sql


def _run_against_sqlite(sql: str, rows):
    """在真 `sqlite3` 上执行**这句真 SQL**（`%s` → `?`），返回命中的 `user_name` 列表。"""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE api_keys ("
        " user_name TEXT, key_hash TEXT, is_active INTEGER, expires_at TEXT)"
    )
    conn.executemany(
        "INSERT INTO api_keys (user_name, key_hash, is_active, expires_at) VALUES (?,?,?,?)",
        rows,
    )
    out = [r[0] for r in conn.execute(sql.replace("%s", "?"), ("hash-x",))]
    conn.close()
    return out


def test_a_null_is_active_row_still_authenticates(captured_sql):
    """🔴 本条的要点：`is_active IS NULL` 的**老行必须照样通过**。

    ⚠️ 迁移里那一列是 `nullable=True` ⇒ 真库里可能有 NULL 行。
       写成 `WHERE is_active = 1` 会让它们**集体失效**，而报错只有一句"凭据无效"。
    """
    rows = [
        ("alice_null", "hash-x", None, "2999-01-01"),   # ← 老行：NULL
        ("bob_off", "hash-x", 0, "2999-01-01"),         # ← 已撤销
        ("carol_on", "hash-x", 1, "2999-01-01"),        # ← 正常
    ]
    assert _run_against_sqlite(captured_sql, rows) == ["alice_null", "carol_on"]


def test_the_predicate_really_excludes_revoked_rows(captured_sql):
    """反面：`is_active = 0` 的**必须被排除** —— 否则"撤销"这个动作是装饰。"""
    rows = [("dave_off", "hash-x", 0, "2999-01-01")]
    assert _run_against_sqlite(captured_sql, rows) == []


def test_the_raw_predicate_would_have_dropped_null_rows(captured_sql):
    """🔴 把结论**取反**：把 `COALESCE(...)` 拆掉 ⇒ 上面第一条**必须变红**。

    ⚠️ 这条用例证明的是「**防 NULL 那半句不是多余的**」，⛔ 不是产品代码 ——
       所以它**不替代**上一条，两条一起才构成"谓词对 + 产品用的就是它"。
    """
    naive = captured_sql.replace("COALESCE(is_active, 1) = 1", "is_active = 1")
    assert naive != captured_sql, "SQL 形状变了 —— 本用例的前提（COALESCE 那半句）不在了"
    rows = [("alice_null", "hash-x", None, "2999-01-01")]
    assert _run_against_sqlite(naive, rows) == []
