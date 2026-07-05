# test_auth.py
def test_login_success(client):
    """测试正常登录"""
    response = client.post("/api/v1/auth/login", json={
        "user_name": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

def test_login_failure(client):
    """测试密码错误"""
    response = client.post("/api/v1/auth/login", json={
        "user_name": "admin",
        "password": "wrong_password"
    })
    assert response.status_code == 401

def test_missing_api_key(client):
    """测试不带API Key访问受保护接口"""
    response = client.post("/api/v1/rag/pg_search", json={
        "question": "test",
        "top_k": 3
    })
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_MISSING"

    assert response.status_code == 401

def test_refresh_token(client):
    """测试Token刷新流程"""
    # 先登录
    login_resp = client.post("/api/v1/auth/login", json={
        "user_name": "admin",
        "password": "admin123"
    })
    refresh_token = login_resp.json()["refresh_token"]
    
    # 用refresh_token获取新access_token
    response = client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_refresh_with_wrong_type(client):
    """测试用access_token去刷新（应该失败）"""
    login_resp = client.post("/api/v1/auth/login", json={
        "user_name": "admin",
        "password": "admin123"
    })
    access_token = login_resp.json()["access_token"]
    
    response = client.post("/api/v1/auth/refresh", json={
        "refresh_token": access_token  # 故意传错类型
    })
    assert response.status_code == 401