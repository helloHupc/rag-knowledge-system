from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_trace_id
from app.core.responses import success_response
from app.schemas.evaluation import DatasetCreateRequest, RunCreateRequest
from app.services.evaluation import EvaluationService


router = APIRouter(prefix="/evaluation", tags=["evaluation"])


# ── Datasets ─────────────────────────────────────────────────────

@router.post("/datasets", response_model=dict)
def create_dataset(
    request: DatasetCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = EvaluationService(session).create_dataset(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/datasets", response_model=dict)
def list_datasets(
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = EvaluationService(session).list_datasets()
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/datasets/{dataset_uuid}", response_model=dict)
def get_dataset(
    dataset_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = EvaluationService(session).get_dataset(str(dataset_uuid))
    return success_response(data.model_dump(mode="json"), trace_id)


@router.delete("/datasets/{dataset_uuid}", response_model=dict)
def delete_dataset(
    dataset_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    EvaluationService(session).delete_dataset(str(dataset_uuid))
    return success_response(None, trace_id)


# ── Runs ─────────────────────────────────────────────────────────

@router.post("/runs", response_model=dict)
def create_run(
    request: RunCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = EvaluationService(session).create_run(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/runs", response_model=dict)
def list_runs(
    dataset_uuid: UUID | None = Query(None, description="Filter by dataset UUID"),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = EvaluationService(session).list_runs(dataset_uuid=str(dataset_uuid) if dataset_uuid else None)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/runs/{run_uuid}", response_model=dict)
def get_run(
    run_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = EvaluationService(session).get_run(str(run_uuid))
    return success_response(data.model_dump(mode="json"), trace_id)


@router.delete("/runs/{run_uuid}", response_model=dict)
def delete_run(
    run_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    EvaluationService(session).delete_run(str(run_uuid))
    return success_response(None, trace_id)
