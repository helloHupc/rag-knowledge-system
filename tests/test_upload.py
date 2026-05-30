from __future__ import annotations

from uuid import UUID

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.ingestion_job import IngestionJob
from app.models.llm_call_log import LlmCallLog


def test_upload_document_success(client, db_session, sample_pdf_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["status"] == "success"
    assert payload["data"]["chunk_count"] >= 1
    assert payload["data"]["doc_uuid"]
    assert payload["data"]["job_uuid"]
    chunks = db_session.query(DocumentChunk).all()
    assert len(chunks) >= 1
    assert all(chunk.vector_id for chunk in chunks)
    document = db_session.query(Document).one()
    assert document.parse_status == "success"
    assert document.index_status == "success"
    llm_logs = db_session.query(LlmCallLog).all()
    assert len(llm_logs) >= 1
    assert all(log.provider_type == "embedding" for log in llm_logs)
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()


def test_upload_document_rejects_unsupported_extension(client):
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": ("notes.exe", b"text-content", "application/octet-stream")},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == 40002


def test_upload_document_rejects_duplicate_hash_and_version(client, sample_pdf_bytes):
    file_payload = ("policy.pdf", sample_pdf_bytes, "application/pdf")

    first = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": file_payload},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": file_payload},
    )
    assert second.status_code == 409
    payload = second.json()
    assert payload["code"] == 40901


def test_upload_document_rejects_invalid_tags_json(client):
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "rule_doc",
            "source_module": "hr",
            "tags": '{"wrong":"shape"}',
        },
        files={"file": ("policy.pdf", b"%PDF-1.4 fake text", "application/pdf")},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == 40001


def test_upload_docx_creates_table_and_text_chunks(client, db_session, sample_docx_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "change_log", "source_module": "hr"},
        files={
            "file": (
                "rules.docx",
                sample_docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "success"

    chunks = db_session.query(DocumentChunk).order_by(DocumentChunk.chunk_index.asc()).all()
    assert len(chunks) >= 2
    assert any(chunk.section_title == "调岗规则" for chunk in chunks)
    assert any(chunk.chunk_type == "table" for chunk in chunks)
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()


def test_upload_xlsx_preserves_sheet_metadata(client, db_session, sample_xlsx_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "config_table", "source_module": "oa"},
        files={
            "file": (
                "config.xlsx",
                sample_xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "success"
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.doc_uuid == doc_uuid).all()
    assert len(chunks) >= 1
    assert chunks[0].sheet_name == "Config"
    assert chunks[0].row_start is not None


def test_upload_txt_document_uses_upload_source_connector(client, db_session):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "note", "source_module": "general"},
        files={"file": ("notes.txt", b"Knowledge base note\nSecond line", "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "success"
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    document = db_session.query(Document).filter(Document.doc_uuid == doc_uuid).one()
    chunk = db_session.query(DocumentChunk).filter(DocumentChunk.doc_uuid == doc_uuid).one()
    assert document.file_ext == "txt"
    assert document.extra_meta["source_connector"] == "upload"
    assert "Knowledge base note" in chunk.chunk_text
    assert chunk.metadata_json["parser"] == "text"


def test_upload_markdown_preserves_headings_with_structural_chunking(client, db_session):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    markdown = b"# Leave Policy\nAnnual leave rules.\n\n## Balance\nCheck the HR system."
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "handbook",
            "source_module": "hr",
            "extra_meta": '{"chunking_strategy":"structural"}',
        },
        files={"file": ("handbook.md", markdown, "text/markdown")},
    )
    assert response.status_code == 200
    payload = response.json()
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.doc_uuid == doc_uuid)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    assert len(chunks) >= 2
    assert {chunk.section_title for chunk in chunks} >= {"Leave Policy", "Balance"}
    assert all(chunk.metadata_json["chunking_strategy"] == "structural" for chunk in chunks)


def test_upload_csv_supports_table_aware_chunking(client, db_session):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    csv_payload = b"name,rule\nannual,release automatically\nparental,release by calculator\n"
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "table",
            "source_module": "hr",
            "extra_meta": '{"chunking_strategy":"table-aware","table_rows_per_chunk":1}',
        },
        files={"file": ("rules.csv", csv_payload, "text/csv")},
    )
    assert response.status_code == 200
    payload = response.json()
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.doc_uuid == doc_uuid)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    assert len(chunks) == 2
    assert all(chunk.chunk_type == "table" for chunk in chunks)
    assert all(chunk.metadata_json["chunking_strategy"] == "table-aware" for chunk in chunks)
    assert all(chunk.metadata_json["table_header"] == "name | rule" for chunk in chunks)


def test_upload_xlsx_table_aware_preserves_header_and_avoids_duplicate_first_row(client, db_session, sample_xlsx_multiline_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "faq_table",
            "source_module": "oa",
            "version": "xlsx-table-aware-upload-test",
            "extra_meta": '{"chunking_strategy":"table-aware","table_rows_per_chunk":2}',
        },
        files={
            "file": (
                "faq.xlsx",
                sample_xlsx_multiline_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.doc_uuid == doc_uuid)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    assert len(chunks) == 2
    assert all(chunk.metadata_json["chunking_strategy"] == "table-aware" for chunk in chunks)
    assert all(chunk.metadata_json["table_render_mode"] == "faq" for chunk in chunks)
    assert "问题：基本咨询" in chunks[0].chunk_text
    assert "补充信息：上传头像失败" in chunks[0].chunk_text
    assert "答案：头像最多24张" in chunks[0].chunk_text
    assert "问题：删除头像" in chunks[1].chunk_text
    assert "补充信息：联系人工处理" in chunks[1].chunk_text
    assert "答案：删除头像和照片" in chunks[1].chunk_text


def test_upload_xlsx_table_aware_inherits_hierarchical_headers_and_tracks_chunk_rows(client, db_session, sample_xlsx_hierarchical_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "faq_table",
            "source_module": "oa",
            "version": "xlsx-hierarchical-table-aware-test",
            "extra_meta": '{"chunking_strategy":"table-aware","table_rows_per_chunk":2,"max_chars":300}',
        },
        files={
            "file": (
                "faq_hierarchical.xlsx",
                sample_xlsx_hierarchical_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.doc_uuid == doc_uuid)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    assert len(chunks) == 2
    assert chunks[0].row_start == 2
    assert chunks[0].row_end == 3
    assert chunks[1].row_start == 4
    assert chunks[1].row_end == 5
    assert "问题：如何修改头像" in chunks[0].chunk_text
    assert "一级分类：基本咨询" in chunks[0].chunk_text
    assert "二级分类：上传头像" in chunks[0].chunk_text
    assert "问题：年龄如何修改" in chunks[1].chunk_text
    assert "二级分类：修改个人信息" in chunks[1].chunk_text


def test_upload_xlsx_table_aware_respects_excel_group_boundaries(client, db_session, sample_xlsx_hierarchical_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "faq_table",
            "source_module": "oa",
            "version": "xlsx-group-boundary-test",
            "extra_meta": '{"chunking_strategy":"table-aware","table_rows_per_chunk":10,"max_chars":500}',
        },
        files={
            "file": (
                "faq_group.xlsx",
                sample_xlsx_hierarchical_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.doc_uuid == doc_uuid)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    assert len(chunks) == 2
    assert chunks[0].row_start == 2
    assert chunks[0].row_end == 3
    assert chunks[1].row_start == 4
    assert chunks[1].row_end == 5
    assert chunks[0].metadata_json["table_group_key"] == ["基本咨询", "上传头像"]
    assert chunks[1].metadata_json["table_group_key"] == ["基本咨询", "修改个人信息"]
    assert chunks[0].metadata_json["table_render_mode"] == "faq"


def test_upload_txt_parent_child_honors_extra_meta_options(client, db_session):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    text = ("ABCDEFGHIJ" * 150).encode("utf-8")
    response = client.post(
        "/api/v1/documents/upload",
        data={
            "source_type": "note",
            "source_module": "general",
            "extra_meta": (
                '{"chunking_strategy":"parent-child","parent_max_chars":1000,'
                '"child_max_chars":800,"overlap_chars":100}'
            ),
        },
        files={"file": ("notes.txt", text, "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    doc_uuid = UUID(payload["data"]["doc_uuid"])

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.doc_uuid == doc_uuid)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    assert len(chunks) == 3
    assert all(chunk.metadata_json["chunking_strategy"] == "parent-child" for chunk in chunks)
    assert [chunk.metadata_json["parent_index"] for chunk in chunks] == [0, 0, 1]
    assert [chunk.metadata_json["child_index"] for chunk in chunks] == [0, 1, 0]


def test_reindex_document_rebuilds_chunks(client, db_session, sample_pdf_bytes):
    upload_response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    doc_uuid = upload_response.json()["data"]["doc_uuid"]

    reindex_response = client.post(f"/api/v1/documents/{doc_uuid}/reindex")
    assert reindex_response.status_code == 200
    payload = reindex_response.json()
    assert payload["data"]["status"] == "success"
    assert payload["data"]["chunk_count"] >= 1

    chunks = db_session.query(DocumentChunk).all()
    assert len(chunks) >= 1
    assert all(chunk.vector_id for chunk in chunks)


def test_upload_document_can_queue_async_job(client, db_session, sample_pdf_bytes, monkeypatch):
    monkeypatch.setenv("INGESTION_MODE", "async")
    from app.core.config import reset_settings_cache

    reset_settings_cache()

    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "pending"
    assert payload["data"]["execution_mode"] == "async"
    assert payload["data"]["chunk_count"] is None
    job_uuid = UUID(payload["data"]["job_uuid"])

    job = db_session.query(IngestionJob).filter(IngestionJob.job_uuid == job_uuid).one()
    assert job.current_step in {"queued", "parsing", "chunking", "embedding", "vector_upsert", "indexed"}


def test_reindex_document_can_queue_async_job(client, db_session, sample_pdf_bytes, monkeypatch):
    upload_response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    doc_uuid = upload_response.json()["data"]["doc_uuid"]

    monkeypatch.setenv("INGESTION_MODE", "async")
    from app.core.config import reset_settings_cache

    reset_settings_cache()

    response = client.post(f"/api/v1/documents/{doc_uuid}/reindex")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "pending"
    assert payload["data"]["execution_mode"] == "async"
