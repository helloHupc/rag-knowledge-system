from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType
from app.models.mixins import TimestampMixin


class SourceSyncItem(TimestampMixin, Base):
    __tablename__ = "source_sync_items"
    __table_args__ = (
        Index("idx_source_sync_items_run_uuid", "run_uuid"),
        Index("idx_source_sync_items_status", "status"),
        Index("idx_source_sync_items_doc_uuid", "doc_uuid"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    run_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("source_sync_runs.run_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    message: Mapped[str | None] = mapped_column(Text)
    doc_uuid: Mapped[uuid.UUID | None] = mapped_column(UuidType)
    job_uuid: Mapped[uuid.UUID | None] = mapped_column(UuidType)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
