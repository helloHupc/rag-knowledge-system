from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.jobs import JobRepository
from app.schemas.jobs import JobListItem
from app.schemas.pagination import PaginatedResponse


class JobManagementService:
    def __init__(self, session: Session) -> None:
        self.jobs = JobRepository(session)

    def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> PaginatedResponse[JobListItem]:
        jobs, total = self.jobs.list_jobs(page=page, page_size=page_size, status=status)
        return PaginatedResponse(
            items=[JobListItem.model_validate(job) for job in jobs],
            total=total,
            page=page,
            page_size=page_size,
        )
