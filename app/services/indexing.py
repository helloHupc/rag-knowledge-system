from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.trace import get_trace_id
from app.integrations.embedding import EmbeddingProvider
from app.integrations.vector_store import VectorStoreClient
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.models.llm_call_log import LlmCallLog
from app.repositories.document_chunks import DocumentChunkRepository
from app.repositories.llm_call_logs import LlmCallLogRepository


logger = logging.getLogger(__name__)


class IndexingService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self.settings = settings
        self.session = session
        self.embedding_provider = EmbeddingProvider(settings)
        self.vector_store = VectorStoreClient(settings)
        self.chunks = DocumentChunkRepository(session)
        self.llm_logs = LlmCallLogRepository(session)

    def index_document(self, document: Document, job: IngestionJob) -> int:
        return self.index_document_with_cleanup(document=document, job=job, stale_chunk_ids=[])

    def index_document_with_cleanup(
        self,
        *,
        document: Document,
        job: IngestionJob,
        stale_chunk_ids: list[str],
    ) -> int:
        chunks = self.chunks.list_for_document(document.doc_uuid)
        if not chunks:
            raise AppError(
                code=ErrorCode.VECTOR_WRITE_FAILED,
                message="no chunks available for indexing",
                status_code=422,
            )

        document.index_status = "running"
        job.current_step = "embedding"
        self.session.commit()

        try:
            if stale_chunk_ids:
                self.vector_store.delete_embeddings(chunk_ids=stale_chunk_ids)

            embeddings = self.embedding_provider.embed_texts([chunk.chunk_text for chunk in chunks])
            self._record_embedding_logs(embeddings)

            job.current_step = "vector_upsert"
            self.session.commit()

            vector_records = self.vector_store.upsert_embeddings(
                embeddings=[item.vector for item in embeddings],
                metadatas=[
                    {
                        "doc_uuid": str(document.doc_uuid),
                        "chunk_uuid": str(chunk.chunk_uuid),
                        "source_type": document.source_type,
                        "source_module": document.source_module,
                        "file_ext": document.file_ext,
                        "version": document.version,
                        "page_no": chunk.page_no,
                        "sheet_name": chunk.sheet_name,
                        "section_title": chunk.section_title,
                        "access_level": document.access_level,
                        "owner_dept": document.owner_dept,
                        "created_at": document.created_at.isoformat(),
                        "updated_at": document.updated_at.isoformat(),
                    }
                    for chunk in chunks
                ],
            )

            chunk_uuid_to_vector = {
                chunk.chunk_uuid: (record.vector_id, record.collection)
                for chunk, record in zip(chunks, vector_records, strict=True)
            }
            self.chunks.update_vector_bindings(chunk_uuid_to_vector)

            document.index_status = "success"
            document.status = "active"
            job.current_step = "indexed"
            job.status = "success"
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            logger.info(
                "Indexed document %s with %s vectors",
                document.doc_uuid,
                len(vector_records),
            )
            return len(vector_records)
        except AppError:
            self._mark_failed(document, job, ErrorCode.VECTOR_WRITE_FAILED, "indexing failed")
            raise
        except Exception as exc:
            logger.exception("Document indexing failed")
            self._mark_failed(document, job, ErrorCode.VECTOR_WRITE_FAILED, str(exc))
            raise AppError(
                code=ErrorCode.VECTOR_WRITE_FAILED,
                message="vector indexing failed",
                status_code=422,
            ) from exc

    def _record_embedding_logs(self, embeddings) -> None:
        trace_id = get_trace_id()
        for embedding in embeddings:
            self.llm_logs.add(
                LlmCallLog(
                    trace_id=trace_id,
                    provider_type="embedding",
                    provider_name=embedding.provider_name,
                    model_name=embedding.model_name,
                    request_type="embed",
                    request_tokens=embedding.request_tokens,
                    response_tokens=None,
                    latency_ms=0,
                    status="success",
                )
            )
        self.session.commit()

    def _mark_failed(
        self,
        document: Document,
        job: IngestionJob,
        error_code: int,
        error_message: str,
    ) -> None:
        self.session.rollback()
        document.index_status = "failed"
        document.status = "failed"
        job.status = "failed"
        job.current_step = "failed"
        job.error_code = str(error_code)
        job.error_message = error_message
        job.finished_at = datetime.now(UTC)
        self.session.commit()
