'''
原来的单独测试，没使用 pytest 框架，
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    """测试根路径健康检查"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_health():
    """测试健康检查接口（不依赖外部服务时可能返回503，这里只测连通性）"""
    response = client.get("/health")
    assert response.status_code in [200, 503]
'''

# test_main.py
def test_root(client):
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_health(client):
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200

def test_docs_accessible(client):
    """测试 Swagger 文档可访问"""
    response = client.get("/docs")
    assert response.status_code == 200