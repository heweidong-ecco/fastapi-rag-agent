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
from config import LOGIN_USER_NAME, LOGIN_PASSWORD

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