from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChunkingStrategyInfo(BaseModel):
    name: str
    params_schema: dict[str, Any] = Field(default_factory=dict)


class ChunkingStrategiesResponse(BaseModel):
    strategies: list[ChunkingStrategyInfo]


class ChunkingPreviewRequest(BaseModel):
    strategy: str = "fixed"
    text: str
    options: dict[str, Any] = Field(default_factory=dict)


class ChunkingDocumentPreviewRequest(BaseModel):
    strategy: str = "fixed"
    options: dict[str, Any] = Field(default_factory=dict)


class ChunkPreviewItem(BaseModel):
    chunk_index: int
    chunk_text: str
    chunk_type: str | None = None
    section_title: str | None = None
    page_no: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    char_count: int
    token_count: int
    chunk_level: str | None = None
    parent_chunk_uuid: str | None = None
    chunk_group_uuid: str | None = None
    context_text: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ChunkingPreviewResponse(BaseModel):
    strategy: str
    total_chunks: int
    chunks: list[ChunkPreviewItem]


class ChunkingDocumentPreviewTextResponse(BaseModel):
    doc_uuid: str
    title: str
    text: str
    char_count: int
    truncated: bool = False
    block_count: int = 0
