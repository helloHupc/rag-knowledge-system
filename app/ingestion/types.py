from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedBlock:
    text: str
    chunk_type: str = "text"
    section_title: str | None = None
    page_no: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ChunkingOptions:
    strategy: str = "fixed"
    max_chars: int = 1200
    overlap_chars: int = 150
    table_rows_per_chunk: int = 20
    parent_max_chars: int = 3000
    child_max_chars: int = 600
    min_chunk_sentences: int = 3
    max_chunk_sentences: int = 20
    similarity_threshold: float = 0.5
    merge_window: int = 3
    topic_gap_minutes: int = 60
    merge_quoted_replies: bool = True


@dataclass(slots=True)
class ChunkPayload:
    chunk_index: int
    chunk_text: str
    chunk_type: str
    section_title: str | None
    page_no: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    token_count: int
    char_count: int
    metadata_json: dict
    parent_chunk_uuid: str | None = None
    chunk_group_uuid: str | None = None
    chunk_level: str | None = None
    context_text: str | None = None
