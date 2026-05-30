from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.responses import success_response
from app.schemas.sources import (
    FolderSyncItem,
    FolderSyncRequest,
    FolderSyncResponse,
    ObjectStorageSyncRequest,
    ObjectStorageSyncResponse,
)
from app.services.source_syncs import SourceSyncService


router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("/folder/sync", response_model=dict)
async def sync_folder_source(
    request: FolderSyncRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    folder_path = _validate_folder_source_path(request.folder_path, settings)
    service = SourceSyncService(session, settings)
    run = await service.sync_folder(request, folder_path)
    detail = service.get_run_detail(run.run_uuid)

    items = _sync_response_items(detail.items)
    skipped = [item.metadata_json for item in detail.items if item.status == "skipped"]

    data = FolderSyncResponse(
        source_name=detail.source_name,
        folder_path=detail.folder_path or "",
        recursive=detail.recursive,
        max_files=detail.max_files,
        total=detail.total_count,
        success_count=detail.success_count,
        failed_count=detail.failed_count,
        skipped_count=detail.skipped_count,
        skipped=skipped,
        items=items,
    )
    payload = data.model_dump(mode="json")
    payload["run_uuid"] = str(detail.run_uuid)
    return success_response(payload, trace_id)


@router.get("/sync-runs", response_model=dict)
def list_sync_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    service = SourceSyncService(session, settings)
    data = service.list_runs(page=page, page_size=page_size, source_type=source_type, status=status)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/object-storage/sync", response_model=dict)
async def sync_object_storage_source(
    request: ObjectStorageSyncRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    service = SourceSyncService(session, settings)
    run = await service.sync_object_storage(request)
    detail = service.get_run_detail(run.run_uuid)

    items = _sync_response_items(detail.items)
    skipped = [item.metadata_json for item in detail.items if item.status == "skipped"]
    data = ObjectStorageSyncResponse(
        source_name=detail.source_name,
        endpoint_url=request.endpoint_url,
        bucket=request.bucket,
        prefix=request.prefix,
        max_files=detail.max_files,
        total=detail.total_count,
        success_count=detail.success_count,
        failed_count=detail.failed_count,
        skipped_count=detail.skipped_count,
        skipped=skipped,
        items=items,
    )
    payload = data.model_dump(mode="json")
    payload["run_uuid"] = str(detail.run_uuid)
    return success_response(payload, trace_id)


@router.get("/sync-runs/{run_uuid}", response_model=dict)
def get_sync_run(
    run_uuid: uuid.UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    service = SourceSyncService(session, settings)
    data = service.get_run_detail(run_uuid)
    return success_response(data.model_dump(mode="json"), trace_id)


def _sync_response_items(items) -> list[FolderSyncItem]:
    return [
        FolderSyncItem(
            file_name=item.file_name,
            relative_path=item.relative_path,
            success=item.status == "success",
            message=item.message or "",
            doc_uuid=item.doc_uuid,
            job_uuid=item.job_uuid,
            status=item.status,
            chunk_count=item.chunk_count,
        )
        for item in items
        if item.status != "skipped"
    ]


def _validate_folder_source_path(folder_path: str, settings: Settings) -> Path:
    if not settings.enable_folder_source:
        raise AppError(
            code=ErrorCode.PERMISSION_DENIED,
            message="folder source is disabled",
            status_code=403,
        )

    resolved_path = Path(folder_path).expanduser().resolve()
    allowed_roots = settings.resolved_folder_source_allowed_roots
    if allowed_roots and not any(_is_relative_to(resolved_path, root) for root in allowed_roots):
        raise AppError(
            code=ErrorCode.PERMISSION_DENIED,
            message="folder path is outside allowed roots",
            status_code=403,
        )
    return resolved_path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
