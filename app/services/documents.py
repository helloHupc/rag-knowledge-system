from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import JobRepository
from app.services.background_jobs import BackgroundJobRunner
from app.services.ingestion import IngestionService
from app.sources.types import SourceDocument
from app.sources.upload import UploadSourceConnector


logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt", "text", "md", "markdown", "html", "htm", "csv", "eml", "jsonl", "chat.jsonl", "jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp"}


class DocumentService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self.settings = settings
        self.session = session
        self.documents = DocumentRepository(session)
        self.jobs = JobRepository(session)

    async def upload_document(
        self,
        *,
        file: UploadFile,
        title: str | None,
        source_type: str,
        source_module: str,
        version: str,
        access_level: str,
        owner_dept: str | None,
        tags: str | None,
        extra_meta: str | None,
    ) -> tuple[Document, IngestionJob, int | None]:
        source_result = await UploadSourceConnector(file).read()
        source_document = source_result.documents[0]

        parsed_tags = self._parse_json_array(tags, "tags")
        parsed_extra_meta = self._parse_json_object(extra_meta, "extra_meta")
        return self.ingest_source_document(
            source_document=source_document,
            title=title,
            source_type=source_type,
            source_module=source_module,
            version=version,
            access_level=access_level,
            owner_dept=owner_dept,
            tags=parsed_tags,
            extra_meta=parsed_extra_meta,
        )

    def ingest_source_document(
        self,
        *,
        source_document: SourceDocument,
        title: str | None,
        source_type: str,
        source_module: str,
        version: str,
        access_level: str,
        owner_dept: str | None,
        tags: list | None = None,
        extra_meta: dict | None = None,
    ) -> tuple[Document, IngestionJob, int | None]:
        extension = self._resolve_extension(source_document.file_name)
        if extension not in ALLOWED_EXTENSIONS:
            raise AppError(
                code=ErrorCode.UNSUPPORTED_FILE_TYPE,
                message="unsupported file type",
            )
        
        # 图片文件需要检查识别服务配置
        IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp"}
        if extension in IMAGE_EXTENSIONS:
            from app.integrations.image_recognition import create_image_recognition_provider
            from app.integrations.image_caption import ImageCaptionProvider
            
            ocr_provider = create_image_recognition_provider(self.settings)
            caption_provider = ImageCaptionProvider(self.settings)
            
            if not ocr_provider.is_configured() and not caption_provider.is_configured():
                raise AppError(
                    code=ErrorCode.INVALID_REQUEST,
                    message="图片识别服务未配置，请先配置 PaddleOCR Token 或多模态 API",
                    status_code=422,
                )

        raw_bytes = source_document.content
        file_size = len(raw_bytes)
        if file_size == 0:
            raise AppError(
                code=ErrorCode.EMPTY_OR_CORRUPTED_FILE,
                message="file is empty or corrupted",
            )

        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if file_size > max_bytes:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"file size exceeds {self.settings.max_upload_size_mb}MB limit",
            )

        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        if self.documents.get_by_hash_and_version(file_hash, version):
            raise AppError(
                code=ErrorCode.DOCUMENT_DUPLICATED,
                message="document already exists",
                status_code=409,
            )

        parsed_tags = tags or []
        parsed_extra_meta = extra_meta or {}

        document = Document(
            title=title or Path(source_document.file_name).stem,
            source_type=source_type,
            source_module=source_module,
            file_name=source_document.file_name,
            file_ext=extension,
            mime_type=source_document.mime_type,
            file_path="",
            file_hash=file_hash,
            file_size=file_size,
            version=version,
            status="active",
            parse_status="pending",
            index_status="pending",
            access_level=access_level,
            owner_dept=owner_dept,
            tags=parsed_tags,
            extra_meta={**source_document.metadata, **parsed_extra_meta},
        )
        self.documents.add(document)

        storage_path = self._build_storage_path(document.doc_uuid.hex, extension, source_document.file_name)
        storage_path.write_bytes(raw_bytes)
        document.file_path = str(storage_path)

        job = IngestionJob(
            doc_uuid=document.doc_uuid,
            job_type="ingest",
            status="pending",
            current_step="queued" if self.settings.ingestion_mode == "async" else "created",
        )
        self.jobs.add(job)

        self.session.commit()
        self.session.refresh(document)
        self.session.refresh(job)
        logger.info("Created document %s and job %s", document.doc_uuid, job.job_uuid)
        if self.settings.ingestion_mode == "async":
            BackgroundJobRunner.submit_ingest_job(
                doc_uuid=document.doc_uuid,
                job_uuid=job.job_uuid,
                settings=self.settings,
            )
            return document, job, None

        chunk_count = IngestionService(self.session, self.settings).process_upload(document, job)
        self.session.refresh(document)
        self.session.refresh(job)
        return document, job, chunk_count

    def _build_storage_path(self, doc_uuid_hex: str, extension: str, original_name: str) -> Path:
        sanitized_name = Path(original_name).name.replace(" ", "_")
        target = self.settings.resolved_raw_data_dir / f"{doc_uuid_hex}_{sanitized_name}"
        if target.suffix.lower().lstrip(".") != extension:
            target = target.with_suffix(f".{extension}")
        return target

    @staticmethod
    def _parse_json_array(raw_value: str | None, field_name: str) -> list:
        if raw_value is None or raw_value == "":
            return []
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"{field_name} must be valid json",
            ) from exc
        if not isinstance(parsed, list):
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"{field_name} must be a json array",
            )
        return parsed

    @staticmethod
    def _resolve_extension(file_name: str) -> str:
        name_lower = file_name.lower()
        if name_lower.endswith(".chat.jsonl"):
            return "chat.jsonl"
        return Path(file_name).suffix.lower().lstrip(".")

    @staticmethod
    def _parse_json_object(raw_value: str | None, field_name: str) -> dict:
        if raw_value is None or raw_value == "":
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"{field_name} must be valid json",
            ) from exc
        if not isinstance(parsed, dict):
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"{field_name} must be a json object",
            )
        return parsed
