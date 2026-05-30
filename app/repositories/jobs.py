from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ingestion_job import IngestionJob


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, job: IngestionJob) -> IngestionJob:
        self.session.add(job)
        self.session.flush()
        return job

    def get_by_uuid(self, job_uuid: uuid.UUID) -> IngestionJob | None:
        stmt = select(IngestionJob).where(IngestionJob.job_uuid == job_uuid)
        return self.session.scalar(stmt)

    def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[IngestionJob], int]:
        stmt = select(IngestionJob)
        count_stmt = select(func.count()).select_from(IngestionJob)

        if status:
            stmt = stmt.where(IngestionJob.status == status)
            count_stmt = count_stmt.where(IngestionJob.status == status)

        stmt = stmt.order_by(IngestionJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        jobs = list(self.session.scalars(stmt))
        total = self.session.scalar(count_stmt) or 0
        return jobs, total
