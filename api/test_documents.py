def test_insert_document(client, auth_headers, sample_document):
    response = client.post("/api/v1/rag/insert",
        headers=auth_headers,
        json=sample_document
    )
    assert response.status_code == 200

def test_insert_batch(client, auth_headers):
    docs = {
        "documents": [
            {"content": "测试文档一", "source": "test"},
            {"content": "测试文档二", "source": "test"},
            {"content": "测试文档三", "source": "test"},
        ]
    }
    response = client.post("/api/v1/rag/insert_batch",
        headers=auth_headers,
        json=docs
    )
    assert response.status_code == 200

def test_delete_document_not_found(client, auth_headers):
    response = client.delete("/api/v1/rag/documents/99999",
        headers=auth_headers
    )
    assert response.status_code == 404