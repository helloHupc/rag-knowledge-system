from __future__ import annotations

from datetime import UTC, datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_session, get_settings_dep, get_trace_id, get_trusted_header_user_context, get_trusted_user_context
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.responses import success_response
from app.core.session_tokens import SessionTokenIssue, create_session_token, verify_session_token
from app.models.auth_session import AuthSession
from app.models.identity import UserAccount
from app.schemas.auth import (
    CurrentUserResponse,
    LogoutResponse,
    SessionTokenResponse,
)
from app.services.identity import IdentityService


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session", response_model=dict)
def create_session(
    request: Request,
    trace_id: str = Depends(get_trace_id),
    trusted_user_context=Depends(get_trusted_header_user_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    if not settings.auth_session_enabled:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="auth session is disabled",
            status_code=401,
        )
    if trusted_user_context is None or not trusted_user_context.is_trusted_identity:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="trusted identity header is required",
            status_code=401,
        )

    resolved = IdentityService(session).resolve_user_context(trusted_user_context)
    if not resolved.is_authenticated:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="user not found or inactive",
            status_code=401,
        )

    user = IdentityService(session).identity.get_user(resolved.user_id)
    assert user is not None
    token_issue = create_session_token(resolved.user_id, settings)
    _record_auth_session(
        session=session,
        token_issue=token_issue,
        user=user,
        auth_method="trusted_header",
        request=request,
    )
    data = SessionTokenResponse(
        access_token=token_issue.access_token,
        expires_in=token_issue.expires_in,
        user_context=resolved,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/logout", response_model=dict)
def logout(
    request: Request,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    if not settings.auth_session_enabled:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="auth session is disabled",
            status_code=401,
        )
    token = _read_bearer_token(request)
    payload = verify_session_token(token, settings)
    if payload.token_id is None:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="session token is not revocable",
            status_code=401,
        )

    auth_session = session.scalar(select(AuthSession).where(AuthSession.token_id == payload.token_id))
    if auth_session is None or auth_session.user_id != payload.user_id:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="session token is not registered",
            status_code=401,
        )
    if auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(UTC)
        auth_session.revoked_reason = "user_logout"
        session.add(auth_session)
        session.commit()

    data = LogoutResponse(user_id=payload.user_id, revoked=True)
    return success_response(data.model_dump(mode="json"), trace_id)


def _record_auth_session(
    *,
    session: Session,
    token_issue: SessionTokenIssue,
    user: UserAccount,
    auth_method: str,
    request: Request,
    external_source: str | None = None,
    external_id: str | None = None,
) -> None:
    client_ip = request.client.host if request.client is not None else None
    user_agent = request.headers.get("User-Agent")
    if user_agent is not None:
        user_agent = user_agent[:256]
    auth_session = AuthSession(
        token_id=token_issue.token_id,
        user_id=user.user_id,
        auth_method=auth_method,
        external_source=external_source or user.external_source,
        external_id=external_id or user.external_id,
        issued_at=token_issue.issued_at,
        expires_at=token_issue.expires_at,
        user_agent=user_agent,
        client_ip=client_ip,
    )
    session.add(auth_session)
    session.commit()


def _read_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.startswith("Bearer "):
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="missing bearer token",
            status_code=401,
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="session token is missing",
            status_code=401,
        )
    return token


@router.get("/me", response_model=dict)
def get_current_user(
    trace_id: str = Depends(get_trace_id),
    trusted_user_context=Depends(get_trusted_user_context),
    session: Session = Depends(get_session),
):
    if trusted_user_context is None:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="authenticated identity is required",
            status_code=401,
        )

    identity_service = IdentityService(session)
    resolved = identity_service.resolve_user_context(trusted_user_context)
    if not resolved.is_authenticated:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="user not found or inactive",
            status_code=401,
        )

    user = identity_service.identity.get_user(resolved.user_id)
    if user is None:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="user not found or inactive",
            status_code=401,
        )

    data = CurrentUserResponse(
        user_uuid=str(user.user_uuid),
        user_id=user.user_id,
        display_name=user.display_name,
        email=user.email,
        employee_no=user.employee_no,
        status=user.status,
        external_source=user.external_source,
        external_id=user.external_id,
        extra_meta=user.extra_meta or {},
        user_context=resolved,
    )
    return success_response(data.model_dump(mode="json"), trace_id)
