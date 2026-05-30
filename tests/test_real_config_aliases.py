from __future__ import annotations

from app.core.config import get_settings, reset_settings_cache


def test_real_config_aliases_are_accepted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/alias-test.sqlite3")
    monkeypatch.delenv("ZILLIZ_URI", raising=False)
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.setenv("ZILLIZ_ENDPOINT", "https://example.zillizcloud.com")
    monkeypatch.setenv("ZILLIZ_TOKEN", "token")
    monkeypatch.setenv("ZILLIZ_COLLECTION_NAME", "alias_collection")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embedding.example.com/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("EMBEDDING_DIM", "2560")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_MODEL", "llm-model")
    monkeypatch.setenv("LLM_MAX_TOKENS", "2000")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")

    reset_settings_cache()
    settings = get_settings()
    assert settings.zilliz_uri == "https://example.zillizcloud.com"
    assert settings.zilliz_collection == "alias_collection"
    assert settings.embedding_api_base == "https://embedding.example.com/v1"
    assert settings.embedding_vector_size == 2560
    assert settings.llm_api_base == "https://llm.example.com/v1"
    assert settings.llm_max_tokens == 2000
    assert settings.llm_temperature == 0.2
    assert settings.vector_store_provider == "zilliz"
    reset_settings_cache()


def test_blank_real_provider_values_fall_back_to_safe_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/alias-test.sqlite3")
    monkeypatch.delenv("ZILLIZ_URI", raising=False)
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.setenv("ZILLIZ_ENDPOINT", " https://example.zillizcloud.com ")
    monkeypatch.setenv("ZILLIZ_TOKEN", " token ")
    monkeypatch.setenv("ZILLIZ_COLLECTION_NAME", "   ")
    monkeypatch.setenv("EMBEDDING_BASE_URL", " https://embedding.example.com/v1 ")
    monkeypatch.setenv("EMBEDDING_API_KEY", " embedding-key ")
    monkeypatch.setenv("EMBEDDING_MODEL", " embedding-model ")
    monkeypatch.setenv("LLM_BASE_URL", " https://llm.example.com/v1 ")
    monkeypatch.setenv("LLM_API_KEY", " llm-key ")
    monkeypatch.setenv("LLM_MODEL", " llm-model ")

    reset_settings_cache()
    settings = get_settings()
    assert settings.zilliz_uri == "https://example.zillizcloud.com"
    assert settings.zilliz_token == "token"
    assert settings.zilliz_collection == "oa_rag_chunks"
    assert settings.embedding_api_base == "https://embedding.example.com/v1"
    assert settings.embedding_api_key == "embedding-key"
    assert settings.embedding_model == "embedding-model"
    assert settings.llm_api_base == "https://llm.example.com/v1"
    assert settings.llm_api_key == "llm-key"
    assert settings.llm_model == "llm-model"
    assert settings.vector_store_provider == "zilliz"
    reset_settings_cache()
