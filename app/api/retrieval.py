from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id, get_trusted_user_context
from app.core.config import Settings, get_settings
from app.core.responses import success_response
from app.schemas.retrieval import (
    RerankConfig,
    SearchRequest,
    StrategiesResponse,
    StrategyInfo,
)
from app.services.retrieval import RetrievalService


router = APIRouter(prefix="/retrieval", tags=["retrieval"])


STRATEGIES = [
    StrategyInfo(
        name="dense",
        label="稠密检索",
        description="仅使用向量语义检索（默认）",
        requires=["embedding"],
    ),
    StrategyInfo(
        name="hybrid",
        label="混合检索",
        description="向量语义检索 + BM25 关键词检索，min‑max 归一化后加权融合",
        requires=["embedding", "sparse_index"],
    ),
]


@router.get("/strategies", response_model=dict)
def list_strategies(
    trace_id: str = Depends(get_trace_id),
):
    settings = get_settings()
    rerank_config = RerankConfig(
        enabled=bool(settings.rerank_enabled and settings.rerank_api_base and settings.rerank_api_key),
        model=settings.rerank_model,
        api_base=settings.rerank_api_base,
    )
    data = StrategiesResponse(strategies=STRATEGIES, rerank=rerank_config)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/search", response_model=dict)
def search(
    request: SearchRequest,
    trace_id: str = Depends(get_trace_id),
    trusted_user_context=Depends(get_trusted_user_context),
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
):
    if trusted_user_context is not None:
        request = request.model_copy(update={"user_context": trusted_user_context})
    data = RetrievalService(session).search(
        request,
        authenticated_identity_required=settings.retrieval_authenticated_identity_required,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/debug-search", response_model=dict)
def debug_search(
    request: SearchRequest,
    trace_id: str = Depends(get_trace_id),
    trusted_user_context=Depends(get_trusted_user_context),
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
):
    if trusted_user_context is not None:
        request = request.model_copy(update={"user_context": trusted_user_context})
    data = RetrievalService(session).debug_search(
        request,
        authenticated_identity_required=settings.retrieval_authenticated_identity_required,
    )
    return success_response(data.model_dump(mode="json"), trace_id)
