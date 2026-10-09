# conftest.py
import os

# 🔴 必须在 `import main` **之前**设置（2026-09-17 · M6 期间实测发现）
#
# 病因：`cost_dashboard.py:218` 在**导入期**就建 Gradio Blocks，Gradio 随即起
#   **非 daemon** 线程去连 `huggingface.co` 发匿名遥测（`gradio/analytics.py`
#   → `huggingface_hub._telemetry._send_telemetry_in_thread`），外加两条
#   `posthog/consumer.py` 上报线程。本机网络不通时它们**卡在 TCP connect 上永不返回**，
#   主线程永远停在 `threading._shutdown` ⇒ **22 条用例全 PASSED，进程却退不出去**。
#
# 实测：不设该开关 → 20s+ 不退出；设了 → 11s 内正常退出（同一个套件）。
# ⚠️ 它会**随机复现**（取决于当次 DNS/TCP 是快速失败还是挂住），不是稳定失败 ——
#   这正是它一直没被发现的原因。卡住的 CI job 会一直耗到超时上限。
#
# ⚠️ 位置不能挪到各测试模块里：`conftest.py` 先于所有测试模块被导入，
#   而本文件第 20 行左右就要 `from main import app` —— 那之后设什么都晚了。
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import pytest
from fastapi.testclient import TestClient
from main import app
from core.config import LOGIN_USER_NAME, LOGIN_PASSWORD


class FakeRedis:
    """假 redis：只实现 `chat_history` 用到的 `rpush` / `lrange` / `expire`（`DEC-055`）。

    🔴 **`lrange` 必须仿真 Redis 语义，⛔ 不能写成 `items[start:end]`** ——
       `get_chat_history` 调的是 `lrange(key, -10, -1)`，而 Python 的 `[-10:-1]`
       **不含最后一个元素**，与真 Redis 的 `LRANGE -10 -1`（**含**）相反
       ⇒ 照抄会让「成对写入」的断言**假红/假绿**。
    """

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.expired: list[tuple[str, int]] = []

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        return items[start:end + 1]          # ← 含 end（Redis 语义）

    def expire(self, key, seconds):
        self.expired.append((key, seconds))

    def history(self, user_name, thread_id):
        """按**契约 C 的键**取历史（`DEC-085`）—— 键里现在是 `(user, thread)` 的复合键。

        🔴 `thread_id` **必填、无默认值**（同产品侧那三个函数）。
           ⛔ **不许给它一个 `"t1"` 之类的默认值**：本仓各测试文件用的会话名并不相同
           （`t-cancel` / `t-sse` / `t-chain` / `t1`），一个"顺手"的默认值会让**读错桶**，
           而 `assert history(...) == []` 那类断言会**静默变绿**（读了个空桶，
           看起来像"确实没写"）—— 那正是 `DEC-056` §六 ③ 裁定的 fail-open 形状。
        """
        import json

        from access.session_key import session_key
        return [
            json.loads(x)
            for x in self.lists.get(f"chat_history:{session_key(user_name, thread_id)}", [])
        ]


@pytest.fixture
def fake_redis():
    """一条用例一个干净的假 redis（⛔ 不碰本机/CI 的真 redis）。"""
    return FakeRedis()


@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    """登录管理员账号，返回 JWT 认证头

    口令从 `config` 读（= `.env` 的 `LOGIN_PASSWORD`），**不硬编码** ——
    见 docs/decisions/DEC-001-认证口令处理路线.md。
    """
    assert LOGIN_PASSWORD, "需在 .env 设置 LOGIN_PASSWORD（应用启动也会因此失败）"
    response = client.post("/api/v1/auth/login", json={
        "user_name": LOGIN_USER_NAME,
        "password": LOGIN_PASSWORD
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def sample_document():
    return {
        "content": "Python是一门强大的编程语言，广泛应用于AI和数据科学领域。",
        "source": "test_docs"
    }

# ══════════════════════════════════════════════════════════════════════
# 🔴 B1 · `DEC-129`：**每条用例前后都清掉角色缓存**
# ══════════════════════════════════════════════════════════════════════
#
# `permission.get_user_role` 带**进程内 TTL 60s 缓存**（它在配额热路径上，
# 一个请求最多调 10 次 —— 见 `app/access/permission.py` 的 docstring）。
#
# ⚠️ **缓存是【进程级】的** ⇒ 它**会跨用例残留**。那会带来两种**都不出声**的坏结果：
#   ① 某条用例先替身出了一个角色 ⇒ 后面真调 `get_user_role` 的用例**拿到那个替身值**；
#   ② 某条用例改了库里的 `role` ⇒ 后面 60 秒内的用例**仍看到旧值**。
# 两者都会让结论**取决于用例的【执行顺序】** —— 而"顺序换了就红/就绿"在本仓是明令要消的形态。
#
# ⇒ 用 autouse fixture 清掉，让每条用例都从**冷缓存**开始。
#    ⚠️ 它**⛔ 不是**"为了让测试过"的开关 —— 缓存本身有 `test_user_role_from_db.py`
#      那 10 条专门钉它（TTL / 写侧失效 / 不误伤别人）。这里清掉的只是**跨用例的脏残留**。
@pytest.fixture(autouse=True)
def _clear_role_cache_between_tests():
    """见上方长注释：消掉「结论随执行顺序变」这个不确定性。"""
    from access.permission import invalidate_role_cache

    invalidate_role_cache()
    yield
    invalidate_role_cache()
