from __future__ import annotations

from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.embedding import EmbeddingProvider
from app.integrations.llm import LlmProvider
from app.integrations.vector_store import VectorStoreClient
from app.schemas.health import HealthStatus


def _status_from_result(ok: bool) -> str:
    return "up" if ok else "down"


class HealthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check(self, db_session: Session) -> HealthStatus:
        postgres_up = False
        redis_up = False

        try:
            db_session.execute(text("SELECT 1"))
            postgres_up = True
        except Exception:
            postgres_up = False

        try:
            Redis.from_url(self.settings.resolved_redis_url).ping()
            redis_up = True
        except Exception:
            redis_up = False

        zilliz_status = "configured" if self.settings.is_external_service_configured("zilliz") else "not_configured"
        embedding_status = (
            "configured"
            if self.settings.is_external_service_configured("embedding_provider")
            else "not_configured"
        )
        llm_status = (
            "configured"
            if self.settings.is_external_service_configured("llm_provider")
            else "not_configured"
        )
        probes = None
        if self.settings.health_probe_external_services:
            probes = {
                "zilliz": "up" if VectorStoreClient(self.settings).probe() else "down",
                "embedding": "up" if EmbeddingProvider(self.settings).probe() else "down",
                "llm_provider": "up" if LlmProvider(self.settings).probe() else "down",
            }

        return HealthStatus(
            app="up",
            postgres=_status_from_result(postgres_up),
            redis=_status_from_result(redis_up),
            zilliz=zilliz_status,
            embedding=embedding_status,
            llm_provider=llm_status,
            probes=probes,
            provider_fallbacks_enabled=self.settings.allow_provider_fallbacks,
            ingestion_mode=self.settings.ingestion_mode,
        )
