from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.config import get_settings
from app.integrations.vector_store import VectorStoreClient
from app.repositories.document_chunks import DocumentChunkRepository
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import JobRepository
from app.schemas.documents import (
    BatchDocumentOperationItem,
    BatchDocumentOperationResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentUpdateRequest,
)
from app.schemas.pagination import PaginatedResponse
from app.services.ingestion import IngestionService
from app.services.sparse_indexing import SparseIndexingService
from app.models.ingestion_job import IngestionJob


class DocumentManagementService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.documents = DocumentRepository(session)
        self.chunks = DocumentChunkRepository(session)
        self.jobs = JobRepository(session)
        self.vector_store = VectorStoreClient(self.settings)
        self.sparse_indexing = SparseIndexingService()

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
    ) -> PaginatedResponse[DocumentListItem]:
        documents, total = self.documents.list_documents(
            page=page,
            page_size=page_size,
            source_type=source_type,
            source_module=source_module,
            parse_status=parse_status,
            index_status=index_status,
            keyword=keyword,
        )
        return PaginatedResponse(
            items=[self._build_document_list_item(document) for document in documents],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_document_detail(self, doc_uuid: UUID) -> DocumentDetail:
        document = self.documents.get_by_uuid(doc_uuid)
        if document is None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )
        chunk_count = self.documents.get_chunk_count(doc_uuid)
        return DocumentDetail(
            **self._build_document_list_item(document).model_dump(),
            file_name=document.file_name,
            file_size=document.file_size,
            file_path=document.file_path,
            tags=document.tags,
            extra_meta=document.extra_meta,
            chunk_count=chunk_count,
        )

    @staticmethod
    def _build_document_list_item(document) -> DocumentListItem:
        return DocumentListItem(
            doc_uuid=document.doc_uuid,
            title=document.title,
            source_type=document.source_type,
            source_module=document.source_module,
            version=document.version,
            parse_status=document.parse_status,
            index_status=document.index_status,
            access_level=document.access_level,
            owner_dept=document.owner_dept,
            created_at=document.created_at,
            updated_at=document.updated_at,
            file_ext=document.file_ext,
            file_exists=Path(document.file_path).exists() if document.file_path else False,
        )

    def require_document(self, doc_uuid: UUID):
        document = self.documents.get_by_uuid(doc_uuid)
        if document is None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )
        return document

    def create_reindex_job(self, doc_uuid: UUID) -> IngestionJob:
        document = self.require_document(doc_uuid)
        job = IngestionJob(
            doc_uuid=document.doc_uuid,
            job_type="reindex",
            status="pending",
            current_step="queued",
        )
        self.jobs.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def update_document(self, doc_uuid: UUID, request: DocumentUpdateRequest) -> DocumentDetail:
        document = self.documents.get_by_uuid(doc_uuid)
        if document is None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )
        self.documents.update_metadata(
            doc_uuid,
            title=request.title,
            source_type=request.source_type,
            source_module=request.source_module,
            version=request.version,
            access_level=request.access_level,
            owner_dept=request.owner_dept,
            tags=request.tags,
            extra_meta=request.extra_meta,
        )
        self.session.commit()
        return self.get_document_detail(doc_uuid)

    def delete_document(self, doc_uuid: UUID) -> None:
        document = self.documents.get_by_uuid(doc_uuid)
        if document is None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )
        chunk_ids = self.chunks.list_chunk_ids_for_document(doc_uuid)
        self.vector_store.delete_embeddings(chunk_ids=chunk_ids)
        self.sparse_indexing.remove_document_chunks(chunk_ids)
        self.chunks.delete_for_document(doc_uuid)
        self.documents.soft_delete(doc_uuid, datetime.now(UTC))
        self.session.commit()
        self._delete_file_if_exists(document.file_path)

    def batch_delete_documents(self, doc_uuids: list[UUID]) -> BatchDocumentOperationResponse:
        items: list[BatchDocumentOperationItem] = []
        for doc_uuid in doc_uuids:
            try:
                self.delete_document(doc_uuid)
                items.append(
                    BatchDocumentOperationItem(
                        doc_uuid=doc_uuid,
                        success=True,
                        message="deleted",
                    )
                )
            except AppError as exc:
                items.append(
                    BatchDocumentOperationItem(
                        doc_uuid=doc_uuid,
                        success=False,
                        message=exc.message,
                    )
                )
        success_count = sum(1 for item in items if item.success)
        return BatchDocumentOperationResponse(
            total=len(items),
            success_count=success_count,
            failed_count=len(items) - success_count,
            items=items,
        )

    def batch_reindex_documents(self, doc_uuids: list[UUID]) -> BatchDocumentOperationResponse:
        items: list[BatchDocumentOperationItem] = []
        ingestion = IngestionService(self.session, self.settings)
        for doc_uuid in doc_uuids:
            try:
                document, job, chunk_count = ingestion.reprocess_document(doc_uuid)
                items.append(
                    BatchDocumentOperationItem(
                        doc_uuid=document.doc_uuid,
                        success=True,
                        message="reindexed",
                        job_uuid=job.job_uuid,
                        chunk_count=chunk_count,
                    )
                )
            except AppError as exc:
                items.append(
                    BatchDocumentOperationItem(
                        doc_uuid=doc_uuid,
                        success=False,
                        message=exc.message,
                    )
                )
        success_count = sum(1 for item in items if item.success)
        return BatchDocumentOperationResponse(
            total=len(items),
            success_count=success_count,
            failed_count=len(items) - success_count,
            items=items,
        )

    @staticmethod
    def _delete_file_if_exists(file_path: str) -> None:
        if not file_path:
            return
        path = Path(file_path)
        if path.exists():
            path.unlink()
