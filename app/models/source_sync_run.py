from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType
from app.models.mixins import TimestampMixin


class SourceSyncRun(TimestampMixin, Base):
    __tablename__ = "source_sync_runs"
    __table_args__ = (
        Index("uq_source_sync_runs_run_uuid", "run_uuid", unique=True),
        Index("idx_source_sync_runs_source_type", "source_type"),
        Index("idx_source_sync_runs_status", "status"),
        Index("idx_source_sync_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    run_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False)
    folder_path: Mapped[str | None] = mapped_column(Text)
    recursive: Mapped[bool] = mapped_column(default=True, server_default="1")
    max_files: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    total_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    summary_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(64))
