"""Integration tests for Knowledge Base & RAG REST API endpoints."""

from app.db.models.enums import KnowledgeSourceType
from fastapi.testclient import TestClient


def test_knowledge_sources_crud_api(client_with_db: TestClient):
    # 1. Create source
    create_payload = {
        "name": "API Test Source",
        "source_type": KnowledgeSourceType.PRODUCT_CATALOG.value,
        "description": "Source created via REST API",
        "is_active": True,
    }
    response = client_with_db.post("/api/v1/knowledge/sources", json=create_payload)
    assert response.status_code == 201
    source_data = response.json()
    assert source_data["name"] == "API Test Source"
    source_id = source_data["id"]

    # 2. Get source
    response = client_with_db.get(f"/api/v1/knowledge/sources/{source_id}")
    assert response.status_code == 200
    assert response.json()["id"] == source_id

    # 3. List sources
    response = client_with_db.get("/api/v1/knowledge/sources")
    assert response.status_code == 200
    list_data = response.json()
    assert list_data["total"] >= 1
    assert any(s["id"] == source_id for s in list_data["items"])


def test_knowledge_documents_and_indexing_api(client_with_db: TestClient):
    # Setup source
    src_res = client_with_db.post(
        "/api/v1/knowledge/sources",
        json={
            "name": "Doc API Source",
            "source_type": KnowledgeSourceType.FAQ.value,
        },
    )
    source_id = src_res.json()["id"]

    # Create document with auto_index=True
    doc_payload = {
        "source_id": source_id,
        "title": "API Luxury Tub Care FAQ",
        "document_type": "FAQ",
        "content": "Regularly clean marble with mild pH neutral soap and soft sponge.",
        "language": "en",
        "metadata": {"category": "Care"},
    }
    response = client_with_db.post("/api/v1/knowledge/documents?auto_index=true", json=doc_payload)
    assert response.status_code == 201
    doc_data = response.json()
    doc_id = doc_data["id"]
    assert doc_data["indexing_status"] == "COMPLETED"

    # Re-index endpoint
    reindex_res = client_with_db.post(f"/api/v1/knowledge/documents/{doc_id}/index")
    assert reindex_res.status_code == 200
    assert reindex_res.json()["indexing_status"] == "COMPLETED"

    # Search endpoint
    search_payload = {
        "query": "How to clean marble tub?",
        "top_k": 3,
    }
    search_res = client_with_db.post("/api/v1/knowledge/search", json=search_payload)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert "results" in search_data
    assert search_data["total_found"] >= 1

    # RAG Query endpoint
    query_payload = {
        "question": "What soap is recommended for marble?",
        "top_k": 2,
    }
    query_res = client_with_db.post("/api/v1/knowledge/query", json=query_payload)
    assert query_res.status_code == 200
    query_data = query_res.json()
    assert query_data["grounded"] is True
    assert len(query_data["sources"]) >= 1
    assert query_data["answer"] is not None
