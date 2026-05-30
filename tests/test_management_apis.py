from __future__ import annotations

from pathlib import Path
import fitz
from uuid import UUID


def _upload_document(client, sample_pdf_bytes, source_module="hr", title=None):
    data = {"source_type": "rule_doc", "source_module": source_module}
    if title:
        data["title"] = title
    response = client.post(
        "/api/v1/documents/upload",
        data=data,
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _build_pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def test_list_documents_returns_uploaded_items(client, sample_pdf_bytes):
    _upload_document(client, sample_pdf_bytes, title="调岗规则")
    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["total"] >= 1
    assert payload["data"]["items"][0]["title"] == "调岗规则"


def test_get_document_detail_returns_chunk_count(client, sample_pdf_bytes):
    # 确保使用同步模式
    from app.core.config import get_settings, reset_settings_cache
    import os
    os.environ["INGESTION_MODE"] = "sync"
    reset_settings_cache()
    
    upload_data = _upload_document(client, sample_pdf_bytes, title="OA规则")
    response = client.get(f"/api/v1/documents/{upload_data['doc_uuid']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["chunk_count"] >= 1
    assert payload["data"]["title"] == "OA规则"
    assert payload["data"]["file_exists"] is True
    assert payload["data"]["file_path"]
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()


def test_delete_document_hides_it_from_detail_query(client, sample_pdf_bytes):
    upload_data = _upload_document(client, sample_pdf_bytes)
    delete_response = client.delete(f"/api/v1/documents/{upload_data['doc_uuid']}")
    assert delete_response.status_code == 200
    detail_response = client.get(f"/api/v1/documents/{upload_data['doc_uuid']}")
    assert detail_response.status_code == 404


def test_delete_document_removes_raw_file(client, sample_pdf_bytes, db_session):
    upload_data = _upload_document(client, sample_pdf_bytes)
    from app.models.document import Document

    document = db_session.query(Document).filter_by(doc_uuid=UUID(upload_data["doc_uuid"])).one()
    file_path = Path(document.file_path)
    assert file_path.exists()

    delete_response = client.delete(f"/api/v1/documents/{upload_data['doc_uuid']}")
    assert delete_response.status_code == 200
    assert not file_path.exists()


def test_download_document_returns_file_before_delete_and_404_after_delete(client, sample_pdf_bytes):
    upload_data = _upload_document(client, sample_pdf_bytes)
    download_response = client.get(f"/api/v1/documents/{upload_data['doc_uuid']}/download")
    assert download_response.status_code == 200
    assert download_response.content

    delete_response = client.delete(f"/api/v1/documents/{upload_data['doc_uuid']}")
    assert delete_response.status_code == 200

    missing_response = client.get(f"/api/v1/documents/{upload_data['doc_uuid']}/download")
    assert missing_response.status_code == 404


def test_reindex_cleans_up_stale_vectors(client, sample_pdf_bytes, monkeypatch):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    upload_data = _upload_document(client, sample_pdf_bytes)
    deleted_chunk_ids = []

    def fake_delete_embeddings(self, *, chunk_ids):
        deleted_chunk_ids.extend(chunk_ids)
        return len(chunk_ids)

    monkeypatch.setattr(
        "app.integrations.vector_store.VectorStoreClient.delete_embeddings",
        fake_delete_embeddings,
    )

    response = client.post(f"/api/v1/documents/{upload_data['doc_uuid']}/reindex")
    assert response.status_code == 200
    assert deleted_chunk_ids
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()


def test_list_jobs_returns_uploaded_job(client, sample_pdf_bytes):
    upload_data = _upload_document(client, sample_pdf_bytes)
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["total"] >= 1
    assert any(item["job_uuid"] == upload_data["job_uuid"] for item in payload["data"]["items"])


def test_update_document_metadata(client, sample_pdf_bytes):
    upload_data = _upload_document(client, sample_pdf_bytes, title="旧标题")
    response = client.patch(
        f"/api/v1/documents/{upload_data['doc_uuid']}",
        json={
            "title": "新标题",
            "source_module": "oa",
            "version": "v2",
            "access_level": "confidential",
            "owner_dept": "finance",
            "tags": ["updated"],
            "extra_meta": {"edited": True},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["title"] == "新标题"
    assert payload["data"]["source_module"] == "oa"
    assert payload["data"]["version"] == "v2"
    assert payload["data"]["access_level"] == "confidential"
    assert payload["data"]["owner_dept"] == "finance"
    assert payload["data"]["tags"] == ["updated"]
    assert payload["data"]["extra_meta"] == {"edited": True}


def test_batch_delete_documents(client, sample_pdf_bytes):
    first = _upload_document(client, sample_pdf_bytes, title="A")
    second = _upload_document(client, _build_pdf_bytes("different content for batch delete"), title="B")
    response = client.post(
        "/api/v1/documents/batch/delete",
        json={
            "doc_uuids": [first["doc_uuid"], second["doc_uuid"]],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total"] == 2
    assert payload["data"]["success_count"] == 2
    assert payload["data"]["failed_count"] == 0


def test_batch_reindex_documents(client, sample_pdf_bytes):
    first = _upload_document(client, sample_pdf_bytes, title="A")
    second = _upload_document(client, _build_pdf_bytes("different content for batch reindex"), title="B")
    response = client.post(
        "/api/v1/documents/batch/reindex",
        json={
            "doc_uuids": [first["doc_uuid"], second["doc_uuid"]],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total"] == 2
    assert payload["data"]["success_count"] == 2
    assert payload["data"]["failed_count"] == 0
    assert all(item["job_uuid"] for item in payload["data"]["items"])
