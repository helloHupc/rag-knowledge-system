from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PrimaryKeyBigInt, UuidType


class LlmCallLog(Base):
    __tablename__ = "llm_call_logs"
    __table_args__ = (
        Index("uq_llm_call_logs_log_uuid", "log_uuid", unique=True),
        Index("idx_llm_call_logs_trace_id", "trace_id"),
        Index("idx_llm_call_logs_provider_type", "provider_type"),
        Index("idx_llm_call_logs_model_name", "model_name"),
        Index("idx_llm_call_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    log_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128))
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    request_tokens: Mapped[int | None] = mapped_column(Integer)
    response_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success", server_default="success")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
