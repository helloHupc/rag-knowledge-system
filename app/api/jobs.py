from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_trace_id
from app.core.responses import success_response
from app.schemas.jobs import JobDetail
from app.services.job_management import JobManagementService
from app.services.jobs import JobService


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=dict)
def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = JobManagementService(session).list_jobs(page=page, page_size=page_size, status=status)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/{job_uuid}", response_model=dict)
def get_job(
    job_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    job = JobService(session).get_job(job_uuid)
    return success_response(JobDetail.model_validate(job).model_dump(mode="json"), trace_id)
