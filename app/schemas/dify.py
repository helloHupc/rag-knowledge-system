from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import AppBaseModel
from app.schemas.qa import GenerationOptions
from app.schemas.retrieval import Citation, RetrievalFilters, UserContext


class DifyKnowledgeRequest(AppBaseModel):
    query: str
    top_k: int = 5
    filters: RetrievalFilters | None = None
    user_context: UserContext | None = None
    generation_options: GenerationOptions | None = None
    response_mode: str = "qa"


class DifyDocumentSummary(AppBaseModel):
    doc_uuid: str
    title: str
    source_module: str
    score: float


class DifyKnowledgeResponseData(AppBaseModel):
    query: str
    mode: str
    answer: str
    answer_status: str
    references: list[Citation]
    documents: list[DifyDocumentSummary]
    filters_applied: dict
    latency_ms: dict[str, int]


class DifyExternalRetrievalSetting(AppBaseModel):
    top_k: int
    score_threshold: float


class DifyExternalMetadataRule(AppBaseModel):
    name: str
    comparison_operator: str
    value: Any | None = None


class DifyExternalMetadataCondition(AppBaseModel):
    logical_operator: Literal["and", "or"] = "and"
    conditions: list[DifyExternalMetadataRule]


class DifyExternalRetrievalRequest(AppBaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: DifyExternalRetrievalSetting
    metadata_condition: DifyExternalMetadataCondition | None = None


class DifyExternalRecord(AppBaseModel):
    content: str
    score: float
    title: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DifyExternalRetrievalResponse(AppBaseModel):
    records: list[DifyExternalRecord]
