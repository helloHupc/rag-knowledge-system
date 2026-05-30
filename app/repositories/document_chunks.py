from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk


class DocumentChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_document(
        self,
        doc_uuid: uuid.UUID,
        chunks: list[DocumentChunk],
    ) -> None:
        self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.doc_uuid == doc_uuid)
        )
        self.session.add_all(chunks)

    def list_chunk_ids_for_document(self, doc_uuid: uuid.UUID) -> list[str]:
        stmt = select(DocumentChunk.chunk_uuid).where(DocumentChunk.doc_uuid == doc_uuid)
        return [str(chunk_uuid) for chunk_uuid in self.session.scalars(stmt)]

    def list_for_document(self, doc_uuid: uuid.UUID) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.doc_uuid == doc_uuid)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        return list(self.session.scalars(stmt))

    def delete_for_document(self, doc_uuid: uuid.UUID) -> None:
        self.session.execute(delete(DocumentChunk).where(DocumentChunk.doc_uuid == doc_uuid))

    def update_vector_bindings(self, chunk_uuid_to_vector: dict[uuid.UUID, tuple[str, str]]) -> None:
        for chunk_uuid, (vector_id, collection) in chunk_uuid_to_vector.items():
            self.session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.chunk_uuid == chunk_uuid)
                .values(vector_id=vector_id, zilliz_collection=collection)
            )
