

import pytest


# test_main.py
def test_root(client):
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@pytest.mark.needs_db
def test_health(client):
    """测试健康检查

    ⚠️ **单条标记 `needs_db`**（本文件其余两条不需要）——
    `/health` 会真去探 Postgres 与 Redis 的连通性，没有库就返回 **503**。
    ⇒ 不进 CI；本机跑时带 `POSTGRES_DB=rag_test`。
    """
    response = client.get("/health")
    assert response.status_code == 200

def test_docs_accessible(client):
    """测试 Swagger 文档可访问"""
    response = client.get("/docs")
    assert response.status_code == 200