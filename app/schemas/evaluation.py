from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import AppBaseModel


# ── Dataset ──────────────────────────────────────────────────────

class DatasetCreateRequest(AppBaseModel):
    name: str
    description: str | None = None
    queries: list["QueryCreateItem"] = []


class QueryCreateItem(AppBaseModel):
    query_text: str
    expected_doc_titles: list[str] = []
    expected_terms: list[str] = []
    notes: str | None = None


class DatasetResponse(AppBaseModel):
    dataset_uuid: str
    name: str
    description: str | None = None
    query_count: int = 0
    created_at: datetime


class DatasetListResponse(AppBaseModel):
    datasets: list[DatasetResponse]


class DatasetDetailResponse(DatasetResponse):
    queries: list["QueryResponse"] = []


class QueryResponse(AppBaseModel):
    query_uuid: str
    query_text: str
    expected_doc_titles: list[str]
    expected_terms: list[str]
    notes: str | None = None


# ── Run ──────────────────────────────────────────────────────────

class RunCreateRequest(AppBaseModel):
    dataset_uuid: str
    chunking_strategy: str = "default"
    chunking_params: dict | None = None
    retrieval_strategy: str = "dense"
    retrieval_params: dict | None = None
    doc_uuids: list[str] = []


class RunResponse(AppBaseModel):
    run_uuid: str
    dataset_uuid: str
    dataset_name: str | None = None
    chunking_strategy: str
    chunking_params: dict
    retrieval_strategy: str
    retrieval_params: dict
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class RunListResponse(AppBaseModel):
    runs: list[RunResponse]


class RunDetailResponse(RunResponse):
    results: list["RunResultResponse"] = []
    summary: "RunSummary | None" = None


class RunResultResponse(AppBaseModel):
    query_uuid: str
    query_text: str
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    mrr: float
    expected_term_hit_rate: float
    avg_latency_ms: int
    top_hits: list[dict]
    debug_info: dict | None = None


class RunSummary(AppBaseModel):
    total_queries: int
    hit_at_1_rate: float
    hit_at_3_rate: float
    hit_at_5_rate: float
    mean_mrr: float
    mean_term_hit_rate: float
    mean_latency_ms: int
