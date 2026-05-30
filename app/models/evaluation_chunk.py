from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType


class EvaluationChunk(Base):
    """Isolated chunk table for evaluation runs.

    Mirrors document_chunks structure but adds run_uuid, no FK to documents
    (prevents polluting the production document_chunks table during evaluation).
    """

    __tablename__ = "evaluation_chunks"
    __table_args__ = (
        Index("uq_evaluation_chunks_chunk_uuid", "chunk_uuid", unique=True),
        Index("idx_evaluation_chunks_run_uuid", "run_uuid"),
        Index("idx_evaluation_chunks_doc_uuid", "doc_uuid"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    chunk_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    run_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    doc_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text", server_default="text")
    section_title: Mapped[str | None] = mapped_column(String(255))
    page_no: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    row_start: Mapped[int | None] = mapped_column(Integer)
    row_end: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int | None] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_summary: Mapped[str | None] = mapped_column(Text)
    vector_id: Mapped[str | None] = mapped_column(String(128))
    zilliz_collection: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
