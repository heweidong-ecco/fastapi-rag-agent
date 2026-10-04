"""`api/cache.py` 的 `chat_history` 落痕口径（`DEC-055` · `docs/待办总表.md` N1）。

🔴 **本文件存在的理由**：`DEC-055` 的全部意义是「**读的人能分辨**这一轮是**说完了**还是**被打断了**」。
判据只有一个 —— 存进去的那条**带不带 `status`、带的是什么**。
⇒ 这条判据**不钉在存储层**（唯一能同时看见三条出口的地方），就只能散到 6 条端点去证，
而那时红的是端点，**看不出是存储层漏了**。

⚠️ **不碰真 redis**：`cache.redis_client` 换成 `conftest.FakeRedis`（`fake_redis` 夹具）。
   本机 `scripts/ci-local.sh` 复用**长期容器 `redis-rag`**，真写会攒 key 且跨用例互相污染。
"""
import json

import pytest

import cache


@pytest.fixture
def fake_store(monkeypatch, fake_redis):
    """把**叶子** `cache.redis_client` 换掉 —— 一个点盖住全部 6 条端点。"""
    monkeypatch.setattr(cache, "redis_client", fake_redis)
    return fake_redis


# ==================== ① `status` 是【必填】的关键字参数 ====================

def test_append_chat_history_writes_status(fake_store):
    cache.append_chat_history("u1", "assistant", "半截", status="cancelled")
    assert fake_store.history("u1") == [
        {"role": "assistant", "content": "半截", "status": "cancelled"},
    ]


def test_append_chat_history_requires_status(fake_store):
    """⛔ 漏传 `status` 必须**当场炸**，⛔ 不许有默认值。

    有默认值 ⇒ 「忘了传」**静默**变成 `done` ⇒ 被打断的一轮会被读成"说完了"
    —— 那正是本 DEC 要防的那类假信号。
    """
    with pytest.raises(TypeError):
        cache.append_chat_history("u1", "user", "问题")


# ==================== ② 老条目（无 `status`）读回 `done` ====================

def test_get_chat_history_defaults_legacy_entries_to_done(fake_store):
    """`DEC-055` 之前写下的条目**没有 `status`** ⇒ 读回补 `"done"`。

    理由：那些条目**只可能是完整答案**（`DEC-053` 之前根本不存半截）。
    ⚠️ 本条同时钉住 `FakeRedis.lrange` 的 **Redis 语义**（`-10/-1` **含**末条）——
       假 redis 若照抄成 Python 切片，**最后一条会凭空消失**，这里立刻红。
    """
    fake_store.rpush("chat_history:u1", json.dumps({"role": "user", "content": "老问题"}))
    cache.append_chat_history("u1", "assistant", "半截", status="error")

    got = cache.get_chat_history("u1")

    assert [e["status"] for e in got] == ["done", "error"]
    assert got[0]["content"] == "老问题"


# ==================== ③ `persist_turn` —— 三条出口共用的一段 ====================

def test_persist_turn_marks_non_done_exit(fake_store):
    """非 `done` ⇒ **成对写** + 助手那条带 `INTERRUPTED_SUFFIX`。"""
    cache.persist_turn("u1", "问题", "  半截答案  ", status="error")
    assert fake_store.history("u1") == [
        {"role": "user", "content": "问题", "status": "error"},
        {"role": "assistant", "content": "半截答案" + cache.INTERRUPTED_SUFFIX, "status": "error"},
    ]


def test_persist_turn_done_keeps_answer_verbatim(fake_store):
    """`done` ⇒ 答案**原样**存（⛔ 不 strip、⛔ 不带标记）。

    带了标记 ⇒ 下一轮会把**好答案**当成"被截断"的。
    """
    cache.persist_turn("u1", "问题", " 完整答案 ", status="done")
    assert fake_store.history("u1") == [
        {"role": "user", "content": "问题", "status": "done"},
        {"role": "assistant", "content": " 完整答案 ", "status": "done"},
    ]


@pytest.mark.parametrize("status", ["done", "cancelled", "error"])
def test_persist_turn_skips_empty_answer(fake_store, status):
    """空答案 ⇒ **一条都不写**（**连提问也不写**）。

    ⛔ 只写提问 ⇒ 历史里留下一条**没有来由**的助手消息（`DEC-053` 决策 4）。
    """
    cache.persist_turn("u1", "问题", "", status=status)
    cache.persist_turn("u1", "问题", "   \n", status=status)
    assert fake_store.history("u1") == []
