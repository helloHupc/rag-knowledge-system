from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import AppBaseModel


class SourceSyncRunListItem(AppBaseModel):
    run_uuid: UUID
    source_type: str
    source_name: str
    source_module: str
    status: str
    total_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class SourceSyncItemDetail(AppBaseModel):
    file_name: str
    relative_path: str | None
    status: str
    message: str | None
    doc_uuid: UUID | None
    job_uuid: UUID | None
    chunk_count: int | None
    metadata_json: dict


class SourceSyncRunDetail(SourceSyncRunListItem):
    folder_path: str | None
    recursive: bool
    max_files: int
    request_json: dict
    summary_json: dict
    items: list[SourceSyncItemDetail]
