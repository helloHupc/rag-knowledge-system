from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType
from app.models.mixins import TimestampMixin


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("uq_document_chunks_chunk_uuid", "chunk_uuid", unique=True),
        Index("idx_document_chunks_doc_uuid", "doc_uuid"),
        Index("idx_document_chunks_page_no", "page_no"),
        Index("idx_document_chunks_sheet_name", "sheet_name"),
        Index("idx_document_chunks_chunk_type", "chunk_type"),
        Index("idx_document_chunks_vector_id", "vector_id"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    chunk_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    doc_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("documents.doc_uuid", ondelete="CASCADE"),
        nullable=False,
    )
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
    parent_chunk_uuid: Mapped[uuid.UUID | None] = mapped_column(UuidType, nullable=True)
    chunk_group_uuid: Mapped[uuid.UUID | None] = mapped_column(UuidType, nullable=True)
    chunk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_id: Mapped[str | None] = mapped_column(String(128))
    zilliz_collection: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
