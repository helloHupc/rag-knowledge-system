from __future__ import annotations

from datetime import datetime

from app.schemas.common import AppBaseModel


class UserContext(AppBaseModel):
    user_id: str
    roles: list[str] = []
    departments: list[str] = []
    is_super_admin: bool = False
    is_authenticated: bool = False
    is_trusted_identity: bool = False
    is_session_identity: bool = False
    is_external_identity: bool = False
    is_jit_user: bool = False


class RetrievalFilters(AppBaseModel):
    source_module: list[str] | None = None
    source_type: list[str] | None = None
    file_ext: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class SearchRequest(AppBaseModel):
    query: str
    top_k: int = 8
    min_score: float = 0.2
    strategy: str = "dense"
    strategy_params: dict | None = None
    filters: RetrievalFilters | None = None
    user_context: UserContext | None = None


class Citation(AppBaseModel):
    doc_uuid: str
    chunk_uuid: str
    title: str
    source_module: str
    page_no: int | None = None
    sheet_name: str | None = None
    section_title: str | None = None
    snippet: str
    version: str
    updated_at: datetime
    score: float
    vector_score: float | None = None
    text_score: float | None = None
    sparse_score: float | None = None
    rerank_score: float | None = None
    pre_rerank_score: float | None = None
    image_url: str | None = None


class SearchResponseData(AppBaseModel):
    query: str
    rewritten_query: str
    filters_applied: dict
    hits: list[Citation]
    latency_ms: int


class DenseHitDebug(AppBaseModel):
    chunk_uuid: str
    doc_uuid: str
    score: float


class SparseHitDebug(AppBaseModel):
    chunk_uuid: str
    doc_uuid: str
    score: float


class DebugSearchResponseData(SearchResponseData):
    raw_filters: dict
    user_context: dict
    ranking_debug: list[dict]
    retrieval_strategy: str = "dense"
    dense_hits: list[DenseHitDebug] = []
    sparse_hits: list[SparseHitDebug] = []
    fusion_alpha: float | None = None
    rerank_enabled: bool = False
    rerank_model: str | None = None
    rerank_latency_ms: int | None = None


class StrategyInfo(AppBaseModel):
    name: str
    label: str
    description: str
    requires: list[str]


class RerankConfig(AppBaseModel):
    enabled: bool = False
    model: str | None = None
    api_base: str | None = None


class StrategiesResponse(AppBaseModel):
    strategies: list[StrategyInfo]
    rerank: RerankConfig
