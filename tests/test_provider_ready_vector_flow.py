from __future__ import annotations

from app.core.config import get_settings
from app.integrations.embedding import EmbeddingProvider
from app.integrations.http_client import post_json_with_retries
from app.integrations.vector_store import VectorStoreClient


def test_local_embedding_provider_is_deterministic():
    settings = get_settings()
    provider = EmbeddingProvider(settings)
    first = provider.embed_texts(["same text"])[0].vector
    second = provider.embed_texts(["same text"])[0].vector
    assert first == second


def test_local_vector_store_can_search_uploaded_vectors():
    settings = get_settings()
    store = VectorStoreClient(settings)
    records = store.upsert_embeddings(
        embeddings=[[0.9, 0.1], [0.1, 0.9]],
        metadatas=[
            {"doc_uuid": "doc-1", "chunk_uuid": "chunk-1", "source_module": "hr"},
            {"doc_uuid": "doc-2", "chunk_uuid": "chunk-2", "source_module": "oa"},
        ],
    )
    assert len(records) == 2

    hits = store.search(
        query_embedding=[0.9, 0.1],
        top_k=1,
        filters={"source_module": ["hr"], "doc_uuid": ["doc-1", "doc-2"]},
    )
    assert len(hits) == 1
    assert hits[0].metadata["chunk_uuid"] == "chunk-1"


def test_zilliz_filter_expression_and_metadata_helpers():
    filters = {
        "doc_uuid": ["doc-1", "doc-2"],
        "source_module": ["hr"],
        "page_no": 3,
        "owner_dept": None,
    }
    expr = VectorStoreClient._build_zilliz_filter_expression(filters)
    assert 'doc_uuid in ["doc-1", "doc-2"]' in expr
    assert 'source_module in ["hr"]' in expr
    assert "page_no == 3" in expr
    assert "owner_dept" not in expr

    metadata = VectorStoreClient._extract_search_metadata(
        {
            "id": "chunk-123",
            "distance": 0.99,
            "entity": {
                "chunk_uuid": "chunk-123",
                "doc_uuid": "doc-1",
                "source_module": "hr",
            },
            "section_title": "Annual Leave",
        }
    )
    assert metadata["chunk_uuid"] == "chunk-123"
    assert metadata["doc_uuid"] == "doc-1"
    assert metadata["source_module"] == "hr"
    assert metadata["section_title"] == "Annual Leave"


def test_http_embedding_payload_includes_encoding_format(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "embedding_provider": "http",
            "embedding_api_base": "https://embedding.example.com/v1",
            "embedding_api_key": "embedding-key",
            "embedding_model": "embedding-model",
        }
    )
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "embedding-model",
                "data": [{"embedding": [0.1, 0.2]}],
            }

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("app.integrations.http_client.httpx.post", fake_post)
    result = EmbeddingProvider(settings).embed_texts(["hello world"])

    assert len(result) == 1
    assert captured["json"]["encoding_format"] == "float"
    assert captured["json"]["input"] == ["hello world"]


def test_http_client_retries_before_success(monkeypatch):
    settings = get_settings().model_copy(update={"provider_retry_count": 2})
    attempts = {"count": 0}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_post(url, headers, json, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary failure")
        return DummyResponse()

    monkeypatch.setattr("app.integrations.http_client.httpx.post", fake_post)
    data = post_json_with_retries(
        settings=settings,
        url="https://example.com",
        headers={},
        payload={"hello": "world"},
        error_factory=lambda exc: RuntimeError(f"wrapped: {exc}"),
    )
    assert data == {"ok": True}
    assert attempts["count"] == 3
