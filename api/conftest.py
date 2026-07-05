# conftest.py
import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    """登录管理员账号，返回 JWT 认证头"""
    response = client.post("/api/v1/auth/login", json={
        "user_name": "admin",
        "password": "admin123"
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

@pytest.fixture
def auth_headers(client):
    response = client.post("/api/v1/auth/login", json={
        "user_name": "admin",
        "password": "admin123"
    })
    print("登录状态码:", response.status_code)
    print("登录响应:", response.json())
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}