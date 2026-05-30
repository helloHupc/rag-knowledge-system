from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        Index("uq_evaluation_results_run_query", "run_uuid", "query_uuid", unique=True),
        Index("idx_evaluation_results_run_uuid", "run_uuid"),
        Index("idx_evaluation_results_query_uuid", "query_uuid"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    run_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("evaluation_runs.run_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    query_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("evaluation_queries.query_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    hit_at_1: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    hit_at_3: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    hit_at_5: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    mrr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    expected_term_hit_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    avg_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    top_hits: Mapped[list] = mapped_column(JsonType, nullable=False, default=list, server_default="[]")
    debug_info: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
