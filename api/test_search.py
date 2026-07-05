def test_pg_search_empty(client, auth_headers):
    response = client.post("/api/v1/rag/pg_search",
        headers=auth_headers,
        json={"question": "Python编程", "top_k": 3}
    )
    assert response.status_code == 200

def test_pg_search_with_data(client, auth_headers, sample_document):
    # 先插入一条
    client.post("/api/v1/rag/insert", headers=auth_headers, json=sample_document)
    response = client.post("/api/v1/rag/pg_search",
        headers=auth_headers,
        json={"question": "Python", "top_k": 3}
    )
    assert response.status_code == 200