from __future__ import annotations


def _upload_sample_document(client, sample_pdf_bytes, *, source_module="hr"):
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": source_module, "owner_dept": "hr"},
        files={"file": ("policy.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["data"]["doc_uuid"]


def test_search_mode_returns_references(client, sample_pdf_bytes):
    """search 模式返回 references 列表"""
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "transfer approval two levels",
            "top_k": 5,
            "response_mode": "search",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["mode"] == "search"
    assert data["query"] == "transfer approval two levels"
    assert data["answer_status"] == "grounded"
    assert len(data["references"]) >= 1
    ref = data["references"][0]
    assert "doc_uuid" in ref
    assert "chunk_uuid" in ref
    assert "title" in ref
    assert "source_module" in ref
    assert "snippet" in ref
    assert "score" in ref
    assert "filters_applied" in data
    assert "latency_ms" in data


def test_qa_mode_returns_answer(client, sample_pdf_bytes):
    """qa 模式返回 answer 文本"""
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "transfer approval two levels",
            "top_k": 5,
            "response_mode": "qa",
            "generation_options": {"temperature": 0.1, "max_tokens": 300},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["mode"] == "qa"
    assert data["answer"]
    assert data["answer_status"] in {"grounded", "insufficient_evidence"}
    assert "references" in data
    assert "latency_ms" in data


def test_search_mode_with_source_module_filter(client, sample_pdf_bytes, sample_docx_bytes):
    """按 source_module 筛选"""
    _upload_sample_document(client, sample_pdf_bytes, source_module="hr")
    # 用不同文件避免去重冲突
    client.post(
        "/api/v1/documents/upload",
        data={"source_type": "rule_doc", "source_module": "finance", "owner_dept": "finance"},
        files={"file": ("finance.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "transfer approval",
            "top_k": 10,
            "response_mode": "search",
            "filters": {"source_module": ["finance"]},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    for ref in data["references"]:
        assert ref["source_module"] == "finance"


def test_search_mode_insufficient_evidence(client, sample_pdf_bytes):
    """无关查询返回 insufficient_evidence"""
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "completely unrelated cafeteria menu today",
            "top_k": 5,
            "min_score": 0.9,
            "response_mode": "search",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["answer_status"] == "insufficient_evidence"
    assert data["references"] == []


def test_default_response_mode_is_search(client, sample_pdf_bytes):
    """不传 response_mode 默认为 search"""
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "transfer approval",
            "top_k": 3,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["mode"] == "search"


def test_invalid_response_mode_rejected(client):
    """非法 response_mode 返回 422"""
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "test",
            "response_mode": "invalid",
        },
    )
    assert response.status_code == 422


def test_search_mode_latency_ms_present(client, sample_pdf_bytes):
    """latency_ms 包含 retrieval 和 total"""
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "transfer approval",
            "response_mode": "search",
        },
    )
    assert response.status_code == 200
    latency = response.json()["data"]["latency_ms"]
    assert "retrieval" in latency
    assert "total" in latency


def test_qa_mode_latency_ms_present(client, sample_pdf_bytes):
    """qa 模式 latency_ms 包含 retrieval、generation、total"""
    _upload_sample_document(client, sample_pdf_bytes)
    response = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "transfer approval",
            "response_mode": "qa",
            "generation_options": {"temperature": 0.1, "max_tokens": 100},
        },
    )
    assert response.status_code == 200
    latency = response.json()["data"]["latency_ms"]
    assert "retrieval" in latency
    assert "total" in latency
