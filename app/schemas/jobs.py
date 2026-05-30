from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import AppBaseModel


class JobDetail(AppBaseModel):
    job_uuid: UUID
    doc_uuid: UUID
    job_type: str
    status: str
    current_step: str
    retry_count: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobListItem(AppBaseModel):
    job_uuid: UUID
    doc_uuid: UUID
    job_type: str
    status: str
    current_step: str
    retry_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
