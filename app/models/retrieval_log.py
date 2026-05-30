from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    __table_args__ = (
        Index("uq_retrieval_logs_log_uuid", "log_uuid", unique=True),
        Index("idx_retrieval_logs_trace_id", "trace_id"),
        Index("idx_retrieval_logs_query_intent", "query_intent"),
        Index("idx_retrieval_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    log_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128))
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    query_intent: Mapped[str | None] = mapped_column(String(64))
    filters_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    user_context_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer)
    generation_latency_ms: Mapped[int | None] = mapped_column(Integer)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer)
    matched_documents_json: Mapped[list] = mapped_column(JsonType, nullable=False, default=list, server_default="[]")
    response_excerpt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
