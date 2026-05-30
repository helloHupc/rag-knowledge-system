from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import AppBaseModel


class DocumentUploadResponse(AppBaseModel):
    doc_uuid: UUID
    job_uuid: UUID
    status: str
    chunk_count: int | None = None
    execution_mode: str = "sync"


class DocumentReindexResponse(AppBaseModel):
    doc_uuid: UUID
    job_uuid: UUID
    status: str
    chunk_count: int
    execution_mode: str = "sync"


class DocumentUpdateRequest(AppBaseModel):
    title: str | None = None
    source_type: str | None = None
    source_module: str | None = None
    version: str | None = None
    access_level: str | None = None
    owner_dept: str | None = None
    tags: list | None = None
    extra_meta: dict | None = None


class BatchDocumentOperationRequest(AppBaseModel):
    doc_uuids: list[UUID]


class BatchDocumentOperationItem(AppBaseModel):
    doc_uuid: UUID
    success: bool
    message: str
    job_uuid: UUID | None = None
    chunk_count: int | None = None


class BatchDocumentOperationResponse(AppBaseModel):
    total: int
    success_count: int
    failed_count: int
    items: list[BatchDocumentOperationItem]


class DocumentListItem(AppBaseModel):
    doc_uuid: UUID
    title: str
    source_type: str
    source_module: str
    version: str
    parse_status: str
    index_status: str
    access_level: str
    owner_dept: str | None
    created_at: datetime
    updated_at: datetime
    file_ext: str = ""
    file_exists: bool = False


class DocumentDetail(DocumentListItem):
    file_name: str
    file_ext: str
    file_size: int | None
    file_path: str | None = None
    file_exists: bool = False
    tags: list
    extra_meta: dict
    chunk_count: int
