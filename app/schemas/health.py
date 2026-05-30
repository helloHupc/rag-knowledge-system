from __future__ import annotations

from app.schemas.common import AppBaseModel


class HealthStatus(AppBaseModel):
    app: str
    postgres: str
    redis: str
    zilliz: str
    embedding: str
    llm_provider: str
    probes: dict | None = None
    provider_fallbacks_enabled: bool = True
    ingestion_mode: str = "sync"
