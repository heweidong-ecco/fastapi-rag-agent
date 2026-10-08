"""`api/tool_cache.py` 的口径守卫（**全离线** —— monkeypatch 掉 redis，⛔ 不碰真 redis）。

**本文件钉住三件事**（`批① 工具缓存收口`）：
  ① **查不到 TTL 必须报错** —— ⛔ 不许 `.get(name, 60)` 那种静默默认值
  ② **`0` = 不缓存**，且**一次 redis 都不碰**（`date_today` 靠它躲开跨天那一小时）
  ③ **失败结果不入缓存** —— 由 `should_cache` 谓词显式决定，⛔ 不靠"猜哪些结果算失败"

⚠️ 它还兼一个**新工具登记网**：`test_every_mcp_registered_tool_has_a_ttl` ——
   以后往 `mcp_server.TOOLS` 加工具却忘了登记 TTL，**只有这条用例会红**。
"""
import pytest

import tool_cache as T


class _FakeRedis:
    """只实现 `tool_cache` 用到的四个方法，并**记下调用**。"""

    def __init__(self):
        self.store = {}
        self.sets = 0

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx:
            if k in self.store:
                return False
            self.store[k] = v
            return True
        self.sets += 1
        self.store[k] = v
        return True

    def delete(self, k):
        self.store.pop(k, None)


@pytest.fixture
def fake(monkeypatch):
    f = _FakeRedis()
    monkeypatch.setattr(T, "redis_client", f)
    return f


def test_get_ttl_unknown_name_raises():
    """🔴 查不到 **抛 KeyError** —— ⛔ 不许 `.get(name, 60)` 那种静默默认。

    反证检验：把断言取反（改成 `== 60`）⇒ 本用例会红 ⇒ 这条尺子在量它该量的事。
    """
    with pytest.raises(KeyError):
        T.get_ttl("这个工具不存在")


def test_every_mcp_registered_tool_has_a_ttl():
    """每一条**已注册给 LLM 的工具**都要有 TTL 条目（含 `0`）。

    ⚠️ 本用例是「新加了工具但忘了登记 TTL」的**唯一**拦网 ——
    跑它才会红；⛔ 别指望 import 期报错（`tool_cache` 不能反向 import `mcp_server`）。
    """
    from mcp_server import TOOLS

    missing = [t["func"].name for t in TOOLS if t["func"].name not in T.TTL_BY_TOOL]
    assert missing == [], f"这些工具没登记 TTL：{missing}"


def test_ttl_zero_never_touches_redis(fake):
    """TTL = 0 ⇒ **直通**：⛔ 一次 redis 都不碰。"""

    calls = []

    @T.cached_tool(name="date_today")
    def _probe():
        calls.append(1)
        return "x"

    assert _probe() == "x"
    assert _probe() == "x"
    assert calls == [1, 1], "TTL=0 时每次都该真执行"
    assert fake.sets == 0, "TTL=0 时⛔ 不该写缓存"


def test_hit_returns_cached_and_skips_body(fake):
    calls = []

    @T.cached_tool(expire_seconds=300, name="calculator")
    def _probe(x):
        calls.append(x)
        return x * 2

    assert _probe(3) == 6
    assert _probe(3) == 6
    assert calls == [3], "第二次该走缓存"


def test_failure_result_is_not_cached(fake):
    """`should_cache` 返回 False ⇒ **不写缓存**（下一次还会真跑）。"""
    calls = []

    @T.cached_tool(
        expire_seconds=300,
        name="web_search",
        should_cache=lambda r: not str(r).startswith("搜索失败"),
    )
    def _probe(q):
        calls.append(q)
        return "搜索失败：网络不通"

    assert _probe("a").startswith("搜索失败")
    assert _probe("a").startswith("搜索失败")
    assert calls == ["a", "a"], "失败结果⛔ 不许被缓存"
