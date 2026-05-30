from __future__ import annotations

from uuid import UUID

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


def _upload_sample_document(client, sample_pdf_bytes):
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "oa", "owner_dept": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["data"]["doc_uuid"]


def _create_identity_user(client, *, user_id: str = "u1001", departments: list[str] | None = None):
    departments = departments or ["hr"]
    for dept_code in departments:
        response = client.post(
            "/api/v1/admin/departments",
            json={"dept_code": dept_code, "dept_name": dept_code},
        )
        assert response.status_code in {200, 409}
    response = client.post(
        "/api/v1/admin/users",
        json={
            "user_id": user_id,
            "display_name": user_id,
            "department_codes": departments,
            "primary_dept_code": departments[0] if departments else None,
        },
    )
    assert response.status_code in {200, 409}


def test_dify_knowledge_qa_mode_returns_grounded_answer(client, sample_pdf_bytes, monkeypatch):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    _create_identity_user(client, user_id="dify-external", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)

    response = client.post(
        "/api/v1/dify/knowledge",
        headers={"Authorization": "Bearer test-dify-key"},
        json={
            "query": "transfer approval two levels",
            "response_mode": "qa",
            "top_k": 5,
            "filters": {"source_module": ["oa"]},
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "qa"
    assert payload["answer_status"] == "grounded"
    assert payload["references"]
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()


def test_dify_knowledge_search_mode_returns_reference_digest(client, sample_pdf_bytes, monkeypatch):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    _create_identity_user(client, user_id="dify-external", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)

    response = client.post(
        "/api/v1/dify/knowledge",
        headers={"Authorization": "Bearer test-dify-key"},
        json={
            "query": "transfer approval two levels",
            "response_mode": "search",
            "top_k": 5,
            "filters": {"source_module": ["oa"]},
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "search"
    assert payload["references"]
    assert payload["documents"]
    assert "policy" in payload["answer"].lower() or "approval" in payload["answer"].lower()
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()


def test_dify_knowledge_rejects_invalid_bearer_token(client, sample_pdf_bytes, monkeypatch):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    _upload_sample_document(client, sample_pdf_bytes)

    response = client.post(
        "/api/v1/dify/knowledge",
        headers={"Authorization": "Bearer wrong-key"},
        json={
            "query": "transfer approval two levels",
            "user_context": {
                "user_id": "u1001",
                "roles": ["hr_admin"],
                "departments": ["hr"],
                "is_super_admin": False,
            },
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == 40101


def test_dify_external_retrieval_returns_raw_records(client, sample_pdf_bytes, monkeypatch):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    _create_identity_user(client, user_id="dify-external", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)

    response = client.post(
        "/api/v1/dify/retrieval",
        headers={"Authorization": "Bearer test-dify-key"},
        json={
            "knowledge_id": "oa",
            "query": "transfer approval two levels",
            "retrieval_setting": {
                "top_k": 3,
                "score_threshold": 0.2,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "records" in payload
    assert "code" not in payload
    assert payload["records"]
    assert payload["records"][0]["title"]
    assert payload["records"][0]["content"]
    assert payload["records"][0]["metadata"]["source_module"] == "oa"


def test_dify_external_retrieval_supports_doc_uuid_knowledge_id(
    client,
    sample_pdf_bytes,
    db_session,
    monkeypatch,
):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    reset_settings_cache()
    _create_identity_user(client, user_id="dify-external", departments=["hr"])
    doc_uuid = _upload_sample_document(client, sample_pdf_bytes)
    document = db_session.query(Document).filter(Document.doc_uuid == UUID(doc_uuid)).one()
    chunk = db_session.query(DocumentChunk).filter(DocumentChunk.doc_uuid == document.doc_uuid).one()
    chunk.chunk_text = "This chunk is only available to the explicit doc uuid path."
    db_session.commit()

    response = client.post(
        "/api/v1/dify/retrieval",
        headers={"Authorization": "Bearer test-dify-key"},
        json={
            "knowledge_id": f"doc_uuid:{doc_uuid}",
            "query": "explicit doc uuid path",
            "retrieval_setting": {
                "top_k": 3,
                "score_threshold": 0.0,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["records"]) == 1
    assert payload["records"][0]["metadata"]["doc_uuid"] == doc_uuid


def test_dify_external_retrieval_rejects_invalid_bearer_token(client, sample_pdf_bytes, monkeypatch):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    _upload_sample_document(client, sample_pdf_bytes)

    response = client.post(
        "/api/v1/dify/retrieval",
        headers={"Authorization": "Bearer wrong-key"},
        json={
            "knowledge_id": "oa",
            "query": "transfer approval two levels",
            "retrieval_setting": {
                "top_k": 3,
                "score_threshold": 0.2,
            },
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == 40101


def test_dify_external_retrieval_returns_empty_records_for_unknown_knowledge_id(
    client,
    sample_pdf_bytes,
    monkeypatch,
):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    monkeypatch.setenv("DIFY_APP_KEY", "test-dify-key")
    reset_settings_cache()
    _create_identity_user(client, user_id="dify-external", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)

    response = client.post(
        "/api/v1/dify/retrieval",
        headers={"Authorization": "Bearer test-dify-key"},
        json={
            "knowledge_id": "finance",
            "query": "transfer approval two levels",
            "retrieval_setting": {
                "top_k": 3,
                "score_threshold": 0.2,
            },
        },
    )
    assert response.status_code == 200
    assert response.json() == {"records": []}


