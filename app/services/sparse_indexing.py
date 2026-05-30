from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.retrieval.sparse_index import SparseIndexProvider


class SparseIndexingService:
    def __init__(self) -> None:
        self.provider = SparseIndexProvider()

    def replace_document_chunks(
        self,
        *,
        document: Document,
        stale_chunk_ids: list[str],
        chunks: list[DocumentChunk],
    ) -> None:
        for chunk_id in stale_chunk_ids:
            self.provider.remove_document(chunk_id)

        for chunk in chunks:
            self.provider.add_document(
                {
                    "chunk_uuid": str(chunk.chunk_uuid),
                    "doc_uuid": str(document.doc_uuid),
                    "chunk_text": chunk.chunk_text,
                    "metadata": {
                        "doc_uuid": str(document.doc_uuid),
                        "chunk_uuid": str(chunk.chunk_uuid),
                        "source_type": document.source_type,
                        "source_module": document.source_module,
                        "file_ext": document.file_ext,
                        "version": document.version,
                        "page_no": chunk.page_no,
                        "sheet_name": chunk.sheet_name,
                        "section_title": chunk.section_title,
                    },
                }
            )

    def remove_document_chunks(self, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            self.provider.remove_document(chunk_id)

    def rebuild_from_database(self, session: Session) -> int:
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.doc_uuid == DocumentChunk.doc_uuid)
            .where(Document.deleted_at.is_(None))
            .where(DocumentChunk.deleted_at.is_(None))
        )
        rows = list(session.execute(stmt))
        self.provider.build_index(
            [
                {
                    "chunk_uuid": str(chunk.chunk_uuid),
                    "doc_uuid": str(document.doc_uuid),
                    "chunk_text": chunk.chunk_text,
                    "metadata": {
                        "doc_uuid": str(document.doc_uuid),
                        "chunk_uuid": str(chunk.chunk_uuid),
                        "source_type": document.source_type,
                        "source_module": document.source_module,
                        "file_ext": document.file_ext,
                        "version": document.version,
                        "page_no": chunk.page_no,
                        "sheet_name": chunk.sheet_name,
                        "section_title": chunk.section_title,
                    },
                }
                for chunk, document in rows
            ]
        )
        return len(rows)

    def ensure_database_indexed(self, session: Session) -> None:
        database_chunk_ids = self._database_chunk_ids(session)
        if self.provider.document_ids != database_chunk_ids:
            self.rebuild_from_database(session)

    def _database_chunk_ids(self, session: Session) -> set[str]:
        stmt = (
            select(DocumentChunk.chunk_uuid)
            .join(Document, Document.doc_uuid == DocumentChunk.doc_uuid)
            .where(Document.deleted_at.is_(None))
            .where(DocumentChunk.deleted_at.is_(None))
        )
        return {str(chunk_uuid) for chunk_uuid in session.scalars(stmt)}
