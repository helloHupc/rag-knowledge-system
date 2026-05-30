from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_hash_and_version(self, file_hash: str, version: str) -> Document | None:
        stmt = select(Document).where(
            Document.file_hash == file_hash,
            Document.version == version,
            Document.deleted_at.is_(None),
            Document.status != "failed",
        )
        return self.session.scalar(stmt)

    def get_by_uuid(self, doc_uuid: uuid.UUID) -> Document | None:
        stmt = select(Document).where(
            Document.doc_uuid == doc_uuid,
            Document.deleted_at.is_(None),
        )
        return self.session.scalar(stmt)

    def list_documents(
        self,
        *,
        page: int,
        page_size: int,
        source_type: str | None = None,
        source_module: str | None = None,
        parse_status: str | None = None,
        index_status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Document], int]:
        stmt = select(Document).where(Document.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))

        filters = []
        if source_type:
            filters.append(Document.source_type == source_type)
        if source_module:
            filters.append(Document.source_module == source_module)
        if parse_status:
            filters.append(Document.parse_status == parse_status)
        if index_status:
            filters.append(Document.index_status == index_status)
        if keyword:
            filters.append(Document.title.ilike(f"%{keyword}%"))

        if filters:
            for criterion in filters:
                stmt = stmt.where(criterion)
                count_stmt = count_stmt.where(criterion)

        stmt = stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        documents = list(self.session.scalars(stmt))
        total = self.session.scalar(count_stmt) or 0
        return documents, total

    def get_chunk_count(self, doc_uuid: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.doc_uuid == doc_uuid,
            DocumentChunk.deleted_at.is_(None),
        )
        return self.session.scalar(stmt) or 0

    def soft_delete(self, doc_uuid: uuid.UUID, deleted_at) -> None:
        self.session.execute(
            update(Document)
            .where(Document.doc_uuid == doc_uuid)
            .values(
                deleted_at=deleted_at,
                status="deleted",
                parse_status="pending",
                index_status="pending",
            )
        )

    def update_metadata(
        self,
        doc_uuid: uuid.UUID,
        *,
        title: str | None = None,
        source_type: str | None = None,
        source_module: str | None = None,
        version: str | None = None,
        access_level: str | None = None,
        owner_dept: str | None = None,
        tags: list | None = None,
        extra_meta: dict | None = None,
    ) -> None:
        values: dict = {}
        if title is not None:
            values["title"] = title
        if source_type is not None:
            values["source_type"] = source_type
        if source_module is not None:
            values["source_module"] = source_module
        if version is not None:
            values["version"] = version
        if access_level is not None:
            values["access_level"] = access_level
        if owner_dept is not None:
            values["owner_dept"] = owner_dept
        if tags is not None:
            values["tags"] = tags
        if extra_meta is not None:
            values["extra_meta"] = extra_meta

        if not values:
            return

        self.session.execute(
            update(Document)
            .where(
                Document.doc_uuid == doc_uuid,
                Document.deleted_at.is_(None),
            )
            .values(**values)
        )

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document
