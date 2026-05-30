from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.models.source_sync_item import SourceSyncItem
from app.models.source_sync_run import SourceSyncRun
from app.repositories.source_sync_runs import SourceSyncRepository
from app.schemas.pagination import PaginatedResponse
from app.schemas.source_sync_history import (
    SourceSyncItemDetail,
    SourceSyncRunDetail,
    SourceSyncRunListItem,
)
from app.schemas.sources import FolderSyncRequest, ObjectStorageSyncRequest
from app.services.documents import ALLOWED_EXTENSIONS, DocumentService
from app.sources.folder import FolderSourceConnector
from app.sources.object_storage import ObjectStorageSourceConnector
from app.sources.types import SourceReadResult


logger = logging.getLogger(__name__)


class SourceSyncService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = SourceSyncRepository(session)
        self.doc_service = DocumentService(settings, session)

    async def sync_folder(self, request: FolderSyncRequest, folder_path: Path) -> SourceSyncRun:
        connector = FolderSourceConnector(
            folder_path,
            recursive=request.recursive,
            allowed_extensions=ALLOWED_EXTENSIONS,
            max_files=request.max_files,
        )
        return await self._sync_connector(
            connector=connector,
            request_json=request.model_dump(mode="json"),
            source_type=request.source_type,
            source_module=request.source_module,
            version=request.version,
            access_level=request.access_level,
            owner_dept=request.owner_dept,
            tags=request.tags,
            extra_meta=request.extra_meta,
            folder_path=str(folder_path),
            recursive=request.recursive,
            max_files=request.max_files,
        )

    async def sync_object_storage(self, request: ObjectStorageSyncRequest) -> SourceSyncRun:
        connector = ObjectStorageSourceConnector(
            endpoint_url=request.endpoint_url,
            bucket=request.bucket,
            access_key=request.access_key,
            secret_key=request.secret_key,
            region=request.region,
            prefix=request.prefix,
            allowed_extensions=ALLOWED_EXTENSIONS,
            max_files=request.max_files,
        )
        request_json = request.model_dump(mode="json")
        request_json["secret_key"] = "***"
        return await self._sync_connector(
            connector=connector,
            request_json=request_json,
            source_type=request.source_type,
            source_module=request.source_module,
            version=request.version,
            access_level=request.access_level,
            owner_dept=request.owner_dept,
            tags=request.tags,
            extra_meta=request.extra_meta,
            folder_path=None,
            recursive=True,
            max_files=request.max_files,
        )

    async def _sync_connector(
        self,
        *,
        connector,
        request_json: dict,
        source_type: str,
        source_module: str,
        version: str,
        access_level: str,
        owner_dept: str | None,
        tags: list,
        extra_meta: dict,
        folder_path: str | None,
        recursive: bool,
        max_files: int,
    ) -> SourceSyncRun:
        run = SourceSyncRun(
            source_type=source_type,
            source_name=connector.name,
            source_module=source_module,
            folder_path=folder_path,
            recursive=recursive,
            max_files=max_files,
            status="running",
            started_at=datetime.now(UTC),
            request_json=request_json,
        )
        self.repo.add_run(run)
        self.session.commit()

        try:
            read_result = await connector.read()
            success_count, failed_count, skipped_count = self._persist_items(
                run=run,
                read_result=read_result,
                source_type=source_type,
                source_module=source_module,
                version=version,
                access_level=access_level,
                owner_dept=owner_dept,
                tags=tags,
                extra_meta=extra_meta,
            )

            total_count = len(read_result.documents)
            run.total_count = total_count
            run.success_count = success_count
            run.failed_count = failed_count
            run.skipped_count = skipped_count
            run.status = self._resolve_run_status(
                total_count=total_count,
                success_count=success_count,
                failed_count=failed_count,
            )
            run.finished_at = datetime.now(UTC)
            run.summary_json = {
                "source_name": read_result.source_name,
                "total_read": total_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
            }
            self.session.commit()
            self.session.refresh(run)
            return run
        except Exception as exc:
            self.session.rollback()
            logger.exception("Source sync run %s failed before completion", run.run_uuid)
            run = self.repo.get_run_by_uuid(run.run_uuid) or run
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.summary_json = {
                "error": str(exc),
            }
            self.session.add(run)
            self.session.commit()
            self.session.refresh(run)
            raise

    def list_runs(
        self, page: int, page_size: int, source_type: str | None = None, status: str | None = None
    ) -> PaginatedResponse[SourceSyncRunListItem]:
        runs, total = self.repo.list_runs(page=page, page_size=page_size, source_type=source_type, status=status)
        return PaginatedResponse(
            items=[SourceSyncRunListItem.model_validate(run) for run in runs],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_run_detail(self, run_uuid: uuid.UUID) -> SourceSyncRunDetail:
        run = self.repo.get_run_by_uuid(run_uuid)
        if not run:
            raise AppError(
                code=ErrorCode.JOB_NOT_FOUND,
                message="sync run not found",
                status_code=404,
            )
        items = self.repo.list_items_by_run(run_uuid)

        return SourceSyncRunDetail(
            **SourceSyncRunListItem.model_validate(run).model_dump(),
            folder_path=run.folder_path,
            recursive=run.recursive,
            max_files=run.max_files,
            request_json=run.request_json,
            summary_json=run.summary_json,
            items=[SourceSyncItemDetail.model_validate(item) for item in items],
        )

    @staticmethod
    def _resolve_run_status(*, total_count: int, success_count: int, failed_count: int) -> str:
        if total_count == 0:
            return "success"
        if failed_count == 0:
            return "success"
        if success_count == 0:
            return "failed"
        return "partial_success"

    def _persist_items(
        self,
        *,
        run: SourceSyncRun,
        read_result: SourceReadResult,
        source_type: str,
        source_module: str,
        version: str,
        access_level: str,
        owner_dept: str | None,
        tags: list,
        extra_meta: dict,
    ) -> tuple[int, int, int]:
        items: list[SourceSyncItem] = []
        success_count = 0
        failed_count = 0

        for source_doc in read_result.documents:
            sync_item = SourceSyncItem(
                run_uuid=run.run_uuid,
                file_name=source_doc.file_name,
                relative_path=source_doc.metadata.get("relative_path"),
                metadata_json=source_doc.metadata,
            )
            try:
                doc, job, chunk_count = self.doc_service.ingest_source_document(
                    source_document=source_doc,
                    title=None,
                    source_type=source_type,
                    source_module=source_module,
                    version=version,
                    access_level=access_level,
                    owner_dept=owner_dept,
                    tags=tags,
                    extra_meta=extra_meta,
                )
                sync_item.status = "success"
                sync_item.message = "ok"
                sync_item.doc_uuid = doc.doc_uuid
                sync_item.job_uuid = job.job_uuid
                sync_item.chunk_count = chunk_count
                success_count += 1
            except AppError as exc:
                self.session.rollback()
                sync_item.status = "failed"
                sync_item.message = exc.message
                failed_count += 1
            except Exception as exc:
                self.session.rollback()
                logger.exception("Unexpected error syncing file %s", source_doc.file_name)
                sync_item.status = "failed"
                sync_item.message = str(exc)
                failed_count += 1
            items.append(sync_item)

        skipped = read_result.metadata.get("skipped", [])
        for skip_info in skipped:
            items.append(
                SourceSyncItem(
                    run_uuid=run.run_uuid,
                    file_name=skip_info.get("file_name", "unknown"),
                    relative_path=skip_info.get("relative_path"),
                    status="skipped",
                    message=skip_info.get("reason", "unknown reason"),
                    metadata_json=skip_info,
                )
            )

        self.repo.add_items(items)
        return success_count, failed_count, len(skipped)
