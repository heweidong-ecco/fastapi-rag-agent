

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