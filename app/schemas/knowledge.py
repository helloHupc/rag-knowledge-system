from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import AppBaseModel
from app.schemas.qa import GenerationOptions
from app.schemas.retrieval import Citation, RetrievalFilters


class KnowledgeQueryRequest(AppBaseModel):
    """通用知识库查询请求

    支持 search（纯检索）和 qa（检索+问答）两种模式。
    """

    query: str
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)
    filters: RetrievalFilters | None = None
    response_mode: Literal["search", "qa"] = "search"
    generation_options: GenerationOptions | None = None


class KnowledgeQueryReference(AppBaseModel):
    """单条引用记录"""

    doc_uuid: str
    chunk_uuid: str
    title: str
    source_module: str
    snippet: str
    score: float
    page_no: int | None = None
    sheet_name: str | None = None
    section_title: str | None = None
    version: str | None = None
    updated_at: str | None = None
    vector_score: float | None = None
    text_score: float | None = None


class KnowledgeQueryResponse(AppBaseModel):
    """通用知识库查询响应"""

    query: str
    mode: Literal["search", "qa"]
    answer: str
    answer_status: str = "grounded"
    references: list[KnowledgeQueryReference] = Field(default_factory=list)
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    latency_ms: dict[str, int] = Field(default_factory=dict)
