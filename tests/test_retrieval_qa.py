from __future__ import annotations

def _upload_sample_document(client, sample_pdf_bytes):
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr", "owner_dept": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["data"]["doc_uuid"]

def _upload_document_with_resource_meta(
    client,
    sample_pdf_bytes,
    *,
    extra_meta: str,
    tags: str | None = None,
    version: str = "v1",
    file_name: str = "resource_policy.pdf",
):
    data = {
        "source_type": "rule_doc",
        "source_module": "hr",
        "owner_dept": "hr",
        "version": version,
        "extra_meta": extra_meta,
    }
    if tags is not None:
        data["tags"] = tags
    response = client.post(
        "/api/v1/documents/upload",
        data=data,
        files={"file": (file_name, sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["data"]["doc_uuid"]

def _upload_document_without_owner(client, sample_pdf_bytes, *, access_level: str):
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr", "access_level": access_level},
        files={"file": (f"{access_level}_policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["data"]["doc_uuid"]

def _upload_sample_docx_document(client, sample_docx_bytes):
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "hr", "owner_dept": "hr"},
        files={
            "file": (
                "policy.docx",
                sample_docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["doc_uuid"]

def _create_identity_user(
    client,
    *,
    user_id: str = "u1001",
    departments: list[str] | None = None,
    roles: list[str] | None = None,
    external_source: str | None = None,
    external_id: str | None = None,
):
    departments = departments or ["hr"]
    roles = roles or ["employee"]
    for dept_code in departments:
        response = client.post(
            "/api/v1/admin/departments",
            json={"dept_code": dept_code, "dept_name": dept_code},
        )
        assert response.status_code in {200, 409}
    for role_code in roles:
        response = client.post(
            "/api/v1/admin/roles",
            json={"role_code": role_code, "role_name": role_code},
        )
        assert response.status_code in {200, 409}
    response = client.post(
        "/api/v1/admin/users",
        json={
            "user_id": user_id,
            "display_name": user_id,
            "department_codes": departments,
            "role_codes": roles,
            "primary_dept_code": departments[0] if departments else None,
            "external_source": external_source,
            "external_id": external_id,
        },
    )
    assert response.status_code in {200, 409}

def _user_context(user_id: str = "u1001") -> dict:
    return {"user_id": user_id}

def test_search_returns_hits_for_authorized_user(client, sample_pdf_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "transfer approval two levels",
            "top_k": 5,
            "filters": {"source_module": ["hr"]},
            "user_context": _user_context("u1001"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert len(payload["data"]["hits"]) >= 1
    assert "vector_score" in payload["data"]["hits"][0]
    assert "text_score" in payload["data"]["hits"][0]
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()
def test_qa_answer_returns_grounded_citations(client, sample_pdf_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/qa/answer",
        headers={"X-Internal-Token": "test-internal-token"},
        json={
            "question": "transfer approval two levels",
            "top_k": 5,
            "filters": {"source_module": ["hr"]},
            "user_context": _user_context("u1001"),
            "generation_options": {"temperature": 0.1, "max_tokens": 300},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["citations"]
    assert payload["data"]["answer_status"] == "grounded"
    assert "基于命中的引用片段" in payload["data"]["answer"]
    
    # 恢复异步模式
    os.environ["INGESTION_MODE"] = "async"
    reset_settings_cache()
def test_qa_answer_rejects_bad_internal_token(client, sample_pdf_bytes):
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/qa/answer",
        headers={"X-Internal-Token": "wrong-token"},
        json={
            "question": "transfer approval two levels",
            "top_k": 5,
            "user_context": {
                "user_id": "u1001",
                "roles": ["hr_admin"],
                "departments": ["hr"],
                "is_super_admin": False,
            },
        },
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == 40101
def test_debug_search_returns_score_breakdown(client, sample_pdf_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/retrieval/debug-search",
        json={
            "query": "transfer approval two levels",
            "top_k": 5,
            "filters": {"source_module": ["hr"]},
            "user_context": _user_context("u1001"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["ranking_debug"]
    assert "vector_score" in payload["data"]["ranking_debug"][0]
    assert "text_score" in payload["data"]["ranking_debug"][0]
def test_qa_answer_returns_insufficient_evidence_for_high_threshold(client, sample_pdf_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/qa/answer",
        headers={"X-Internal-Token": "test-internal-token"},
        json={
            "question": "completely unrelated cafeteria menu",
            "top_k": 5,
            "filters": {"source_module": ["hr"]},
            "user_context": _user_context("u1001"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["answer_status"] == "insufficient_evidence"
    assert "未找到足够依据" in payload["data"]["answer"]
def test_search_supports_natural_chinese_query(client, sample_docx_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    _upload_sample_docx_document(client, sample_docx_bytes)
    response = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "调岗申请的二级审批是怎么要求的？",
            "top_k": 5,
            "filters": {"source_module": ["hr"]},
            "user_context": _user_context("u1001"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["hits"]
    assert payload["data"]["hits"][0]["text_score"] > 0
def test_search_source_module_filter_is_case_insensitive(client, sample_docx_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "OA", "owner_dept": "hr"},
        files={
            "file": (
                "policy.docx",
                sample_docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200

    response = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "调岗申请的二级审批是怎么要求的？",
            "top_k": 5,
            "filters": {"source_module": ["oa"]},
            "user_context": _user_context("u1001"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["hits"]
def test_qa_answer_supports_natural_chinese_question(client, sample_docx_bytes):
    # 确保使用同步模式
    import os
    os.environ["INGESTION_MODE"] = "sync"
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    _create_identity_user(client, user_id="u1001", departments=["hr"])
    _upload_sample_docx_document(client, sample_docx_bytes)
    response = client.post(
        "/api/v1/qa/answer",
        headers={"X-Internal-Token": "test-internal-token"},
        json={
            "question": "调岗申请的二级审批是怎么要求的？",
            "top_k": 5,
            "filters": {"source_module": ["hr"]},
            "user_context": _user_context("u1001"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["answer_status"] == "grounded"
    assert payload["data"]["citations"]

def _create_evaluation_dataset(client) -> str:
    response = client.post(
        "/api/v1/evaluation/datasets",
        json={
            "name": "permission-aware-eval",
            "queries": [
                {
                    "query_text": "transfer approval two levels",
                    "expected_terms": ["approval"],
                }
            ],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["dataset_uuid"]

def _run_evaluation(client, dataset_uuid: str) -> dict:
    response = client.post(
        "/api/v1/evaluation/runs",
        json={
            "dataset_uuid": dataset_uuid,
            "retrieval_strategy": "dense",
        },
    )
    assert response.status_code == 200
    run = response.json()["data"]
    assert run["status"] == "completed"

    detail_response = client.get(f"/api/v1/evaluation/runs/{run['run_uuid']}")
    assert detail_response.status_code == 200
    return detail_response.json()["data"]
