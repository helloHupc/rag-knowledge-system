from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.integrations.embedding import EmbeddingProvider
from app.integrations.llm import LlmProvider


def test_embedding_provider_falls_back_to_local_when_enabled(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "embedding_api_base": "https://embedding.example.com/v1",
            "embedding_api_key": "embedding-key",
            "embedding_model": "embedding-model",
            "allow_provider_fallbacks": True,
        }
    )

    def raise_error(*args, **kwargs):
        raise AppError(
            code=ErrorCode.EMBEDDING_FAILED,
            message="remote embedding down",
            status_code=422,
        )

    monkeypatch.setattr(EmbeddingProvider, "_embed_via_http", raise_error)
    result = EmbeddingProvider(settings).embed_texts(["hello world"])
    assert len(result) == 1
    assert result[0].provider_name == "local"


def test_embedding_provider_raises_when_fallback_disabled(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "embedding_api_base": "https://embedding.example.com/v1",
            "embedding_api_key": "embedding-key",
            "embedding_model": "embedding-model",
            "allow_provider_fallbacks": False,
        }
    )

    def raise_error(*args, **kwargs):
        raise AppError(
            code=ErrorCode.EMBEDDING_FAILED,
            message="remote embedding down",
            status_code=422,
        )

    monkeypatch.setattr(EmbeddingProvider, "_embed_via_http", raise_error)
    try:
        EmbeddingProvider(settings).embed_texts(["hello world"])
    except AppError as exc:
        assert exc.code == ErrorCode.EMBEDDING_FAILED
    else:
        raise AssertionError("expected AppError when provider fallback is disabled")


def test_llm_provider_falls_back_to_local_answer_builder(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "llm_api_base": "https://llm.example.com/v1",
            "llm_api_key": "llm-key",
            "llm_model": "llm-model",
            "allow_provider_fallbacks": True,
        }
    )
    provider = LlmProvider(settings)

    def raise_error(*args, **kwargs):
        raise AppError(
            code=ErrorCode.LLM_GENERATION_FAILED,
            message="remote llm down",
            status_code=422,
        )

    monkeypatch.setattr(provider, "generate_answer", raise_error)
    result = provider.generate_answer_with_fallback(
        question="审批流程是什么？",
        citations=[],
        generation_options=None,
        fallback_builder=lambda citations: "fallback answer",
    )
    assert result is not None
    assert result.provider_name == "local-fallback"
    assert result.answer == "fallback answer"


def test_llm_provider_raises_when_fallback_disabled(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "llm_api_base": "https://llm.example.com/v1",
            "llm_api_key": "llm-key",
            "llm_model": "llm-model",
            "allow_provider_fallbacks": False,
        }
    )
    provider = LlmProvider(settings)

    def raise_error(*args, **kwargs):
        raise AppError(
            code=ErrorCode.LLM_GENERATION_FAILED,
            message="remote llm down",
            status_code=422,
        )

    monkeypatch.setattr(provider, "generate_answer", raise_error)
    try:
        provider.generate_answer_with_fallback(
            question="审批流程是什么？",
            citations=[],
            generation_options=None,
            fallback_builder=lambda citations: "fallback answer",
        )
    except AppError as exc:
        assert exc.code == ErrorCode.LLM_GENERATION_FAILED
    else:
        raise AssertionError("expected AppError when provider fallback is disabled")
