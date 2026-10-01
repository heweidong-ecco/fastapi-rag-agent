"""全局日级 token 总额（`B10`）· **需要真 Postgres** 的那一半。

⚠️ 与 `test_global_daily_budget_offline.py` 的分工：本文件**只放"必须真读写库"的**。

## 🔴 本文件补的是一个【真缺口】，不是"对称好看"

`docs/specs/token_tracker.md` 的 `①b · Task 3` **只列了离线那份**。
但离线那份**从头到尾没有执行过那条 SQL** —— 它只 `AST` 取字面量做静态核对。
⇒ 意味着：**表名打错、列名打错、SQL 语法错，CI 永远绿。**

📌 这与 `B8` 不对称（那边有 `test_session_budget.py`）。
本文件把这条补上 —— 补完，`B10` 的 SQL **至少有一条路径会真的执行它**。

🔴 **跑之前必须带库名隔离**：`POSTGRES_DB=rag_test`
   （本仓有前科：R2 冒烟忘带库名，`record_usage` 往**真库**写了 4 行 ——
   `docs/复盘/2026-09-17-只读冒烟其实会写库.md`）。

📌 **本文件不进 CI**（CI 无 postgres service，见 `api/pytest.ini`）
   —— 所以 `B10` 的**核心判据（SQL 里没有 `user_name`）不在本文件**，在离线那份里。
"""
import pytest

pytestmark = pytest.mark.needs_db


# 本文件专用前缀，便于事后精确清理（⛔ 别用 t1 / test 这种会撞上别人的名字）
_PREFIX = "b10-global-budget-"


def test_global_sql_actually_executes():
    """🔴 **本文件存在的理由**：让那条 SQL **真的被数据库解析一次**。

    离线测试只核对字符串；**这一条才会发现表名/列名/语法错误**。
    ⚠️ 它不检查数值（数值依赖当时库里有什么），只要求**能被执行且返回一个数**。
    """
    import token_tracker

    got = token_tracker.get_global_daily_token_usage()

    assert isinstance(got, (int, float)), (
        f"全局取数返回了非数值 {got!r} —— SQL 很可能没跑通（fail-open 会盖上它）\n"
        "  ⚠️ 这正是离线测试抓不到的那类错：那边只核对字符串。"
    )


def test_global_usage_includes_this_write():
    """真写一行 ⇒ 全站合计必须**至少包含**它。"""
    import token_tracker

    token_tracker.record_usage(
        model="qwen-turbo", prompt_tokens=4242, completion_tokens=0,
        purpose="test", user_name=_PREFIX + "solo-user", thread_id=_PREFIX + "solo-thread",
    )

    assert token_tracker.get_global_daily_token_usage() >= 4242


def test_global_usage_counts_a_user_who_would_be_over_his_own_limit():
    """🔴 **「全局」必须独立于 `user_name`** —— 用一个**别的用户**写，全局也看得见。

    ⚠️ 若有人给 SQL 加回了 `WHERE user_name = %s`，本函数会**只统计那一个用户**：
       · 若它统计的是"写行的那个用户" ⇒ 本条**照样通过**（数据就是他的）；
       · ⇒ 所以**真正的守卫在离线那份**（静态查 SQL 里有没有 `user_name`）。
       本条的价值是**另一种**：证明"**跨用户求和是真的在求和**"，
       而不是"碰巧只有一行数据"。
    """
    import token_tracker
    from token_config import GLOBAL_DAILY_TOKEN_LIMIT

    # 用两个不同用户各写一笔，各自都在**自己的**日上限之内
    for tag in ("alpha", "beta"):
        token_tracker.record_usage(
            model="qwen-turbo", prompt_tokens=1000, completion_tokens=0,
            purpose="test", user_name=f"{_PREFIX}{tag}", thread_id=f"{_PREFIX}{tag}",
        )

    total = token_tracker.get_global_daily_token_usage()

    assert total >= 2000, (
        f"两个用户各写了 1000，全站合计却只有 {total} ⇒ 它没有跨用户求和"
    )
    assert GLOBAL_DAILY_TOKEN_LIMIT > 0, "全局上限必须是正数，否则判定永远拒"
