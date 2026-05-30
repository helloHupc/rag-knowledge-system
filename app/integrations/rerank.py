"""Rerank provider – OpenAI‑compatible /rerank endpoint + local text‑overlap fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.http_utils import build_openai_compatible_url

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RerankResult:
    index: int
    score: float
    document: str | None = None


class BaseRerankProvider:
    """Abstract base for rerank providers."""

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RerankResult]:
        raise NotImplementedError

    def probe(self) -> bool:
        return True


class HttpRerankProvider(BaseRerankProvider):
    """OpenAI‑compatible /rerank endpoint (e.g. Cohere, Jina, Voyage)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._api_base = settings.rerank_api_base or ""
        self._api_key = settings.rerank_api_key or ""
        self._model = settings.rerank_model or ""

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RerankResult]:
        if not documents:
            return []
        if not self._api_base or not self._api_key:
            raise AppError(
                code=ErrorCode.RETRIEVAL_FAILED,
                message="rerank provider is not configured",
                status_code=422,
            )

        started = perf_counter()
        url = build_openai_compatible_url(self._api_base, "/rerank")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self._model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.settings.provider_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RETRIEVAL_FAILED,
                message=f"rerank request failed: {exc}",
                status_code=422,
            ) from exc

        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info("Rerank via HTTP completed in %sms", elapsed_ms)

        results_raw = data.get("results", [])
        return [
            RerankResult(
                index=r.get("index", 0),
                score=float(r.get("relevance_score", 0.0)),
                document=r.get("document"),
            )
            for r in results_raw
        ]

    def probe(self) -> bool:
        if not self._api_base or not self._api_key:
            return False
        try:
            self.rerank("probe", ["test document"])
            return True
        except Exception:
            logger.exception("Rerank probe failed")
            return False


class LocalRerankProvider(BaseRerankProvider):
    """Text‑overlap fallback reranker using normalized word overlap."""

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[RerankResult]:
        if not documents:
            return []

        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return [
                RerankResult(index=i, score=0.0, document=doc)
                for i, doc in enumerate(documents)
            ]

        results: list[RerankResult] = []
        for i, doc in enumerate(documents):
            doc_tokens = self._tokenize(doc)
            if not doc_tokens:
                score = 0.0
            else:
                overlap = sum(1 for t in doc_tokens if t in query_tokens)
                score = round(overlap / len(doc_tokens), 6)
            results.append(RerankResult(index=i, score=score, document=doc))

        results.sort(key=lambda r: r.score, reverse=True)
        if top_n is not None:
            results = results[:top_n]
        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import re

        text = text.lower().strip()
        tokens: list[str] = []
        cjk_chars = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i : i + 2])
        ascii_tokens = re.findall(r"[a-z0-9]+", re.sub(r"[\u4e00-\u9fff]", " ", text))
        tokens.extend(ascii_tokens)
        return tokens


def create_rerank_provider(settings: Settings) -> BaseRerankProvider:
    """Factory: returns HttpRerankProvider if configured, otherwise LocalRerankProvider."""
    if settings.rerank_enabled and settings.rerank_api_base and settings.rerank_api_key:
        return HttpRerankProvider(settings)
    return LocalRerankProvider()
