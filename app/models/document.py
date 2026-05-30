from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import JsonType, PrimaryKeyBigInt, UuidType
from app.db.base import Base
from app.models.mixins import TimestampMixin


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("uq_documents_doc_uuid", "doc_uuid", unique=True),
        Index("idx_documents_source_module", "source_module"),
        Index("idx_documents_source_type", "source_type"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_parse_status", "parse_status"),
        Index("idx_documents_index_status", "index_status"),
        Index("idx_documents_access_level", "access_level"),
        Index("idx_documents_owner_dept", "owner_dept"),
        Index("idx_documents_created_at", "created_at"),
        Index("idx_documents_file_hash", "file_hash"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    doc_uuid: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        default=uuid.uuid4,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_ext: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1", server_default="v1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    access_level: Mapped[str] = mapped_column(String(64), nullable=False, default="internal", server_default="internal")
    owner_dept: Mapped[str | None] = mapped_column(String(64))
    owner_role: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list] = mapped_column(JsonType, nullable=False, default=list, server_default="[]")
    extra_meta: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    created_by: Mapped[str | None] = mapped_column(String(64))
    updated_by: Mapped[str | None] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
