from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("uq_evaluation_runs_run_uuid", "run_uuid", unique=True),
        Index("idx_evaluation_runs_dataset_uuid", "dataset_uuid"),
        Index("idx_evaluation_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    run_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    dataset_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("evaluation_datasets.dataset_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    chunking_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="default", server_default="default")
    chunking_params: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    retrieval_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="dense", server_default="dense")
    retrieval_params: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
