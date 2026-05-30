from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id, get_trusted_user_context
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.responses import success_response
from app.schemas.qa import AnswerRequest
from app.services.qa import QaService


router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/answer", response_model=dict)
def answer(
    request: AnswerRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    trusted_user_context=Depends(get_trusted_user_context),
    x_internal_token: str | None = Header(default=None),
):
    if x_internal_token is not None and x_internal_token != settings.internal_token:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="invalid internal token",
            status_code=401,
        )
    if trusted_user_context is not None:
        request = request.model_copy(update={"user_context": trusted_user_context})
    data = QaService(session).answer(
        request,
        authenticated_identity_required=settings.retrieval_authenticated_identity_required,
    )
    return success_response(data.model_dump(mode="json"), trace_id)
