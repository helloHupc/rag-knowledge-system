from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import AppBaseModel


class FolderSyncRequest(AppBaseModel):
    folder_path: str
    recursive: bool = True
    max_files: int = Field(default=100, ge=1, le=1000)
    source_type: str
    source_module: str
    version: str = "v1"
    access_level: str = "internal"
    owner_dept: str | None = None
    tags: list = Field(default_factory=list)
    extra_meta: dict = Field(default_factory=dict)


class ObjectStorageSyncRequest(AppBaseModel):
    endpoint_url: str
    bucket: str
    prefix: str = ""
    region: str = "us-east-1"
    access_key: str
    secret_key: str
    max_files: int = Field(default=100, ge=1, le=1000)
    source_type: str = "object_storage"
    source_module: str
    version: str = "v1"
    access_level: str = "internal"
    owner_dept: str | None = None
    tags: list = Field(default_factory=list)
    extra_meta: dict = Field(default_factory=dict)


class FolderSyncItem(AppBaseModel):
    file_name: str
    relative_path: str | None = None
    success: bool
    message: str
    doc_uuid: UUID | None = None
    job_uuid: UUID | None = None
    status: str | None = None
    chunk_count: int | None = None


class FolderSyncResponse(AppBaseModel):
    source_name: str
    folder_path: str
    recursive: bool
    max_files: int
    total: int
    success_count: int
    failed_count: int
    skipped_count: int
    skipped: list[dict]
    items: list[FolderSyncItem]


class ObjectStorageSyncResponse(AppBaseModel):
    source_name: str
    endpoint_url: str
    bucket: str
    prefix: str
    max_files: int
    total: int
    success_count: int
    failed_count: int
    skipped_count: int
    skipped: list[dict]
    items: list[FolderSyncItem]
