from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType


class EvaluationQuery(Base):
    __tablename__ = "evaluation_queries"
    __table_args__ = (
        Index("uq_evaluation_queries_query_uuid", "query_uuid", unique=True),
        Index("idx_evaluation_queries_dataset_uuid", "dataset_uuid"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    query_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    dataset_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        ForeignKey("evaluation_datasets.dataset_uuid", ondelete="CASCADE"),
        nullable=False,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_doc_titles: Mapped[list] = mapped_column(JsonType, nullable=False, default=list, server_default="[]")
    expected_terms: Mapped[list] = mapped_column(JsonType, nullable=False, default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text)
