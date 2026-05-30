from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_settings_dep, get_trace_id
from app.core.config import Settings
from app.core.responses import success_response


router = APIRouter(tags=["system"])


@router.get("/configs", response_model=dict)
def get_configs(
    trace_id: str = Depends(get_trace_id),
    settings: Settings = Depends(get_settings_dep),
):
    data = {
        "app_env": settings.app_env,
        "app_port": settings.app_port,
        "provider_timeout_seconds": settings.provider_timeout_seconds,
        "provider_retry_count": settings.provider_retry_count,
        "health_probe_external_services": settings.health_probe_external_services,
        "allow_provider_fallbacks": settings.allow_provider_fallbacks,
        "ingestion_mode": settings.ingestion_mode,
        "enable_folder_source": settings.enable_folder_source,
        "folder_source_allowed_roots": [
            str(path) for path in settings.resolved_folder_source_allowed_roots
        ],
        "vector_store_provider": settings.vector_store_provider,
        "zilliz_collection": settings.zilliz_collection,
        "embedding_model": settings.embedding_model or "not-configured",
        "embedding_vector_size": settings.embedding_vector_size,
        "llm_provider": "http" if settings.llm_api_base and settings.llm_api_key and settings.llm_model else "local",
        "llm_model": settings.llm_model or "local-placeholder-answer",
        "dify_base_url": settings.dify_base_url,
    }
    return success_response(data, trace_id)
