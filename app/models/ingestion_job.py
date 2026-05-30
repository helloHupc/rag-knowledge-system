from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PrimaryKeyBigInt, UuidType
from app.models.mixins import TimestampMixin


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("uq_ingestion_jobs_job_uuid", "job_uuid", unique=True),
        Index("idx_ingestion_jobs_doc_uuid", "doc_uuid"),
        Index("idx_ingestion_jobs_status", "status"),
        Index("idx_ingestion_jobs_current_step", "current_step"),
        Index("idx_ingestion_jobs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    job_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    doc_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("documents.doc_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default="ingest", server_default="ingest")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    current_step: Mapped[str] = mapped_column(String(64), nullable=False, default="created", server_default="created")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(64))
