from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.http_client import post_json_with_retries
from app.integrations.http_utils import build_openai_compatible_url


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmbeddingResult:
    text: str
    vector: list[float]
    model_name: str
    provider_name: str
    request_tokens: int


class EmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        if self.settings.embedding_api_base and self.settings.embedding_api_key:
            try:
                return self._embed_via_http(texts)
            except AppError:
                if not self.settings.allow_provider_fallbacks:
                    raise
                logger.warning("Embedding provider failed; falling back to local deterministic embeddings")
        
        # Fallback: local deterministic embedding (for testing only)
        logger.warning("Using local deterministic embedding - not suitable for production")
        return self._embed_locally(texts)

    def probe(self) -> bool:
        if self.settings.embedding_api_base and self.settings.embedding_api_key:
            try:
                self.embed_texts(["probe"])
                return True
            except AppError:
                logger.exception("Embedding probe failed")
                return False
        return True  # local mode always works

    def _embed_locally(self, texts: list[str]) -> list[EmbeddingResult]:
        import hashlib
        results: list[EmbeddingResult] = []
        model_name = self.settings.embedding_model or "local-deterministic"
        provider_name = "local"
        vector_size = self.settings.embedding_vector_size

        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw_values = list(digest)
            if vector_size > len(raw_values):
                repeats = (vector_size // len(raw_values)) + 1
                raw_values = (raw_values * repeats)[:vector_size]
            else:
                raw_values = raw_values[:vector_size]
            vector = [round(value / 255.0, 6) for value in raw_values]
            results.append(
                EmbeddingResult(
                    text=text,
                    vector=vector,
                    model_name=model_name,
                    provider_name=provider_name,
                    request_tokens=len(text.split()),
                )
            )

        logger.info("Generated %s local embedding vectors", len(results))
        return results

    _BATCH_SIZE = 32

    def _embed_via_http(self, texts: list[str]) -> list[EmbeddingResult]:
        started = perf_counter()
        request_url = build_openai_compatible_url(self.settings.embedding_api_base, "/embeddings")
        headers = {
            "Authorization": f"Bearer {self.settings.embedding_api_key}",
            "Content-Type": "application/json",
        }

        # Batch to avoid provider limits (e.g. ModelScope caps at ~64 per call)
        all_results: list[EmbeddingResult] = []
        model_name: str | None = None
        provider_name = self.settings.embedding_api_base
        batch_size = max(self.settings.image_recognition_batch_size, self._BATCH_SIZE) \
            if hasattr(self.settings, 'image_recognition_batch_size') else self._BATCH_SIZE
        batch_size = self._BATCH_SIZE

        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            payload = {
                "model": self.settings.embedding_model,
                "input": batch,
                "encoding_format": "float",
            }
            data = post_json_with_retries(
                settings=self.settings,
                url=request_url,
                headers=headers,
                payload=payload,
                error_factory=lambda exc: AppError(
                    code=ErrorCode.EMBEDDING_FAILED,
                    message=f"embedding provider request failed: {exc}",
                    status_code=422,
                ),
            )
            raw_vectors = data.get("data") or []
            if len(raw_vectors) != len(batch):
                raise AppError(
                    code=ErrorCode.EMBEDDING_FAILED,
                    message="embedding provider returned unexpected result size",
                    status_code=422,
                )
            if model_name is None:
                model_name = data.get("model") or self.settings.embedding_model or "remote-embedding"
            for text, item in zip(batch, raw_vectors, strict=True):
                all_results.append(
                    EmbeddingResult(
                        text=text,
                        vector=item.get("embedding", []),
                        model_name=model_name,
                        provider_name=provider_name,
                        request_tokens=len(text.split()),
                    )
                )

        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info("Fetched %s embedding vectors via HTTP in %sms", len(all_results), elapsed_ms)
        return all_results
