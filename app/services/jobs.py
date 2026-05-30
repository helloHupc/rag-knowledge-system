from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.ingestion_job import IngestionJob
from app.repositories.jobs import JobRepository


class JobService:
    def __init__(self, session: Session) -> None:
        self.jobs = JobRepository(session)

    def get_job(self, job_uuid: UUID) -> IngestionJob:
        job = self.jobs.get_by_uuid(job_uuid)
        if job is None:
            raise AppError(code=ErrorCode.JOB_NOT_FOUND, message="job not found", status_code=404)
        return job
