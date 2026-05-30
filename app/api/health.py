from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id
from app.core.config import Settings
from app.core.responses import success_response
from app.schemas.health import HealthStatus
from app.services.health import HealthService


router = APIRouter(tags=["system"])


@router.get("/health", response_model=dict)
def health_check(
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    data: HealthStatus = HealthService(settings).check(session)
    return success_response(data.model_dump(), trace_id)
