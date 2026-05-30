from __future__ import annotations

from app.core.config import get_settings
from app.services.health import HealthService


def test_health_check_returns_statuses(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["app"] == "up"
    assert payload["data"]["postgres"] == "up"
    assert payload["data"]["zilliz"] in {"configured", "not_configured"}
    assert "provider_fallbacks_enabled" in payload["data"]
    assert payload["trace_id"].startswith("trc_")


def test_health_can_include_probe_results(monkeypatch, db_session):
    settings = get_settings().model_copy(
        update={
            "health_probe_external_services": True,
            "zilliz_uri": "https://example.zillizcloud.com",
            "zilliz_token": "token",
            "embedding_api_base": "https://embedding.example.com/v1",
            "embedding_api_key": "embedding-key",
            "embedding_model": "embedding-model",
            "llm_api_base": "https://llm.example.com/v1",
            "llm_api_key": "llm-key",
            "llm_model": "llm-model",
        }
    )
    monkeypatch.setattr("app.services.health.VectorStoreClient.probe", lambda self: True)
    monkeypatch.setattr("app.services.health.EmbeddingProvider.probe", lambda self: False)
    monkeypatch.setattr("app.services.health.LlmProvider.probe", lambda self: True)

    result = HealthService(settings).check(db_session)
    assert result.probes == {
        "zilliz": "up",
        "embedding": "down",
        "llm_provider": "up",
    }


def test_llm_probe_returns_false_when_not_configured():
    settings = get_settings().model_copy(
        update={
            "llm_api_base": None,
            "llm_api_key": None,
            "llm_model": None,
        }
    )

    from app.integrations.llm import LlmProvider

    assert LlmProvider(settings).probe() is False


def test_llm_probe_returns_true_when_http_probe_succeeds(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "llm_api_base": "https://llm.example.com/v1",
            "llm_api_key": "llm-key",
            "llm_model": "llm-model",
        }
    )

    monkeypatch.setattr(
        "app.integrations.llm.post_json_with_retries",
        lambda **kwargs: {
            "choices": [
                {
                    "message": {
                        "content": "pong",
                    }
                }
            ]
        },
    )

    from app.integrations.llm import LlmProvider

    assert LlmProvider(settings).probe() is True


def test_llm_probe_returns_false_when_http_probe_raises(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "llm_api_base": "https://llm.example.com/v1",
            "llm_api_key": "llm-key",
            "llm_model": "llm-model",
        }
    )

    def raise_probe_error(**kwargs):
        from app.core.errors import AppError, ErrorCode

        raise AppError(
            code=ErrorCode.LLM_GENERATION_FAILED,
            message="probe failed",
            status_code=422,
        )

    monkeypatch.setattr("app.integrations.llm.post_json_with_retries", raise_probe_error)

    from app.integrations.llm import LlmProvider

    assert LlmProvider(settings).probe() is False


def test_configs_exposes_runtime_provider_settings(client):
    response = client.get("/api/v1/configs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert "provider_timeout_seconds" in payload["data"]
    assert "provider_retry_count" in payload["data"]
    assert "health_probe_external_services" in payload["data"]
    assert "allow_provider_fallbacks" in payload["data"]
    assert "enable_folder_source" in payload["data"]
    assert "folder_source_allowed_roots" in payload["data"]
    assert "embedding_vector_size" in payload["data"]
