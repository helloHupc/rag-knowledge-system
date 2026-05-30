from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.ingestion.chunking import build_chunks
from app.ingestion.types import ChunkingOptions
from app.ingestion.parser_registry import ParserRegistry
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.ingestion_job import IngestionJob
from app.repositories.document_chunks import DocumentChunkRepository
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import JobRepository
from app.services.indexing import IndexingService
from app.services.sparse_indexing import SparseIndexingService


logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, session: Session, settings=None) -> None:
        self.session = session
        self.settings = settings
        self.documents = DocumentRepository(session)
        self.jobs = JobRepository(session)
        self.chunks = DocumentChunkRepository(session)
        self.parser_registry = ParserRegistry()
        self.sparse_indexing = SparseIndexingService()

    def process_upload(self, document: Document, job: IngestionJob) -> int:
        return self.process_upload_with_cleanup(document=document, job=job, stale_chunk_ids=[])

    def process_upload_with_cleanup(
        self,
        *,
        document: Document,
        job: IngestionJob,
        stale_chunk_ids: list[str],
    ) -> int:
        document.status = "processing"
        document.parse_status = "running"
        job.status = "running"
        job.current_step = "parsing"
        job.started_at = datetime.now(UTC)
        self.session.commit()

        try:
            file_path = Path(document.file_path)
            parsed_blocks = self.parser_registry.parse(document.file_ext, file_path)
            if not parsed_blocks:
                raise AppError(
                    code=ErrorCode.DOCUMENT_PARSE_FAILED,
                    message="document parser produced no text blocks",
                    status_code=422,
                )

            job.current_step = "chunking"
            self.session.commit()

            chunk_options = self._build_chunking_options(document)
            chunk_payloads = build_chunks(
                parsed_blocks,
                options=chunk_options,
            )
            if not chunk_payloads:
                raise AppError(
                    code=ErrorCode.CHUNKING_FAILED,
                    message="chunking produced no chunks",
                    status_code=422,
                )

            chunk_models = [
                DocumentChunk(
                    chunk_uuid=uuid.uuid4(),
                    doc_uuid=document.doc_uuid,
                    chunk_index=payload.chunk_index,
                    chunk_type=payload.chunk_type,
                    section_title=payload.section_title,
                    page_no=payload.page_no,
                    sheet_name=payload.sheet_name,
                    row_start=payload.row_start,
                    row_end=payload.row_end,
                    token_count=payload.token_count,
                    char_count=payload.char_count,
                    chunk_text=payload.chunk_text,
                    metadata_json=payload.metadata_json,
                    parent_chunk_uuid=(
                        uuid.UUID(payload.parent_chunk_uuid) if payload.parent_chunk_uuid else None
                    ),
                    chunk_group_uuid=(
                        uuid.UUID(payload.chunk_group_uuid) if payload.chunk_group_uuid else None
                    ),
                    chunk_level=payload.chunk_level,
                    context_text=payload.context_text,
                )
                for payload in chunk_payloads
            ]

            self.chunks.replace_for_document(document.doc_uuid, chunk_models)
            self.sparse_indexing.replace_document_chunks(
                document=document,
                stale_chunk_ids=stale_chunk_ids,
                chunks=chunk_models,
            )
            document.status = "active"
            document.parse_status = "success"
            document.index_status = "pending"
            self.session.commit()
            if self.settings is not None:
                indexed_count = IndexingService(self.settings, self.session).index_document_with_cleanup(
                    document=document,
                    job=job,
                    stale_chunk_ids=stale_chunk_ids,
                )
            else:
                indexed_count = 0
                job.status = "success"
                job.current_step = "chunking_completed"
                job.finished_at = datetime.now(UTC)
                self.session.commit()
            logger.info(
                "Parsed document %s into %s chunks",
                document.doc_uuid,
                len(chunk_models),
            )
            return len(chunk_models) if indexed_count >= 0 else len(chunk_models)
        except AppError as exc:
            self._mark_failed(document.doc_uuid, job.job_uuid, exc.message, str(exc.code))
            raise
        except Exception as exc:
            logger.exception("Document ingestion failed")
            self._mark_failed(
                document.doc_uuid,
                job.job_uuid,
                str(exc),
                str(ErrorCode.DOCUMENT_PARSE_FAILED),
            )
            raise AppError(
                code=ErrorCode.DOCUMENT_PARSE_FAILED,
                message="document parsing failed",
                status_code=422,
            ) from exc

    def reprocess_document(self, doc_uuid: uuid.UUID) -> tuple[Document, IngestionJob, int]:
        document = self.documents.get_by_uuid(doc_uuid)
        if document is None or document.deleted_at is not None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )

        job = IngestionJob(
            doc_uuid=document.doc_uuid,
            job_type="reindex",
            status="pending",
            current_step="created",
        )
        self.jobs.add(job)
        self.session.commit()
        self.session.refresh(job)
        stale_chunk_ids = self.chunks.list_chunk_ids_for_document(document.doc_uuid)
        chunk_count = self.process_upload_with_cleanup(
            document=document,
            job=job,
            stale_chunk_ids=stale_chunk_ids,
        )
        return document, job, chunk_count

    def resume_job(self, *, doc_uuid: uuid.UUID, job_uuid: uuid.UUID) -> int:
        document = self.documents.get_by_uuid(doc_uuid)
        job = self.jobs.get_by_uuid(job_uuid)
        if document is None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )
        if job is None:
            raise AppError(
                code=ErrorCode.JOB_NOT_FOUND,
                message="job not found",
                status_code=404,
            )
        stale_chunk_ids = self.chunks.list_chunk_ids_for_document(document.doc_uuid) if job.job_type == "reindex" else []
        return self.process_upload_with_cleanup(
            document=document,
            job=job,
            stale_chunk_ids=stale_chunk_ids,
        )

    def _mark_failed(
        self,
        doc_uuid: uuid.UUID,
        job_uuid: uuid.UUID,
        error_message: str,
        error_code: str,
    ) -> None:
        self.session.rollback()
        document = self.documents.get_by_uuid(doc_uuid)
        job = self.jobs.get_by_uuid(job_uuid)
        if document is None or job is None:
            return
        
        # 删除已上传的文件
        if document.file_path:
            try:
                file_path = Path(document.file_path)
                if file_path.exists():
                    file_path.unlink()
                    logger.info("Deleted failed upload file: %s", file_path)
            except Exception as e:
                logger.warning("Failed to delete upload file: %s", e)
        
        document.status = "failed"
        document.parse_status = "failed"
        job.status = "failed"
        job.current_step = "failed"
        job.error_code = error_code
        job.error_message = error_message
        job.finished_at = datetime.now(UTC)
        self.session.commit()

    @staticmethod
    def _get_chunking_strategy(document: Document) -> str:
        value = document.extra_meta.get("chunking_strategy") if document.extra_meta else None
        return str(value).strip() if value else "fixed"

    @staticmethod
    def _build_chunking_options(document: Document) -> ChunkingOptions:
        extra_meta = document.extra_meta or {}
        return ChunkingOptions(
            strategy=IngestionService._get_chunking_strategy(document),
            max_chars=IngestionService._read_int_option(extra_meta, "max_chars", default=1200, minimum=100, maximum=8000),
            overlap_chars=IngestionService._read_int_option(extra_meta, "overlap_chars", default=150, minimum=0, maximum=2000),
            table_rows_per_chunk=IngestionService._read_int_option(
                extra_meta,
                "table_rows_per_chunk",
                default=20,
                minimum=1,
                maximum=500,
            ),
            parent_max_chars=IngestionService._read_int_option(
                extra_meta,
                "parent_max_chars",
                default=3000,
                minimum=1000,
                maximum=8000,
            ),
            child_max_chars=IngestionService._read_int_option(
                extra_meta,
                "child_max_chars",
                default=600,
                minimum=200,
                maximum=2000,
            ),
            min_chunk_sentences=IngestionService._read_int_option(
                extra_meta,
                "min_chunk_sentences",
                default=3,
                minimum=1,
                maximum=50,
            ),
            max_chunk_sentences=IngestionService._read_int_option(
                extra_meta,
                "max_chunk_sentences",
                default=20,
                minimum=2,
                maximum=100,
            ),
            similarity_threshold=IngestionService._read_float_option(
                extra_meta,
                "similarity_threshold",
                default=0.5,
                minimum=0.0,
                maximum=1.0,
            ),
            merge_window=IngestionService._read_int_option(
                extra_meta,
                "merge_window",
                default=3,
                minimum=1,
                maximum=10,
            ),
        )

    @staticmethod
    def _read_int_option(
        extra_meta: dict,
        key: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        value = extra_meta.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _read_float_option(
        extra_meta: dict,
        key: str,
        *,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        value = extra_meta.get(key)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(parsed, maximum))
