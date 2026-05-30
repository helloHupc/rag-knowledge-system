from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.core.session_tokens import verify_session_token
from app.db.session import get_db_session
from app.models.auth_session import AuthSession
from app.repositories.identity import IdentityRepository
from app.schemas.retrieval import UserContext


def get_settings_dep() -> Settings:
    return get_settings()


def get_trace_id(request: Request) -> str:
    return request.state.trace_id


def get_session(session: Session = Depends(get_db_session)) -> Session:
    return session


def get_trusted_user_context(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
) -> UserContext | None:
    session_user_id = _read_user_id_from_session_token(request=request, settings=settings, session=session)
    if session_user_id is not None:
        return UserContext(user_id=session_user_id, is_session_identity=True)

    return get_trusted_header_user_context(request=request, settings=settings, session=session)


def get_trusted_header_user_context(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
) -> UserContext | None:
    if not settings.trusted_identity_header_enabled:
        return None

    user_id = _read_user_id_from_headers(
        request=request,
        header_names=settings.trusted_identity_user_headers,
    )
    if user_id is not None:
        return UserContext(user_id=user_id, is_trusted_identity=True)

    external_source = _read_user_id_from_headers(
        request=request,
        header_names=settings.trusted_identity_external_source_headers,
    )
    external_id = _read_user_id_from_headers(
        request=request,
        header_names=settings.trusted_identity_external_id_headers,
    )
    if external_source is not None and external_id is not None:
        user = IdentityRepository(session).get_user_by_external_identity(
            external_source=external_source,
            external_id=external_id,
        )
        if user is not None:
            return UserContext(user_id=user.user_id, is_trusted_identity=True, is_external_identity=True)
        return UserContext(
            user_id=f"external:{external_source}:{external_id}",
            is_trusted_identity=True,
            is_external_identity=True,
        )
    return None


def require_admin_actor(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
) -> str | None:
    if not settings.admin_auth_enabled:
        return None

    user_id = _read_user_id_from_session_token(request=request, settings=settings, session=session)
    if user_id is None:
        trusted_context = _read_trusted_admin_context(request=request, settings=settings, session=session)
        user_id = trusted_context.user_id if trusted_context is not None else None
    if user_id is None:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="admin identity is required",
            status_code=401,
        )

    identity = IdentityRepository(session)
    user = identity.get_user(user_id)
    if user is None or user.status != "active":
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="admin user not found or inactive",
            status_code=401,
        )

    allowed_roles = {
        item.strip()
        for item in settings.admin_auth_allowed_roles.split(",")
        if item.strip()
    }
    
    # 简化：直接检查用户角色（从用户表或配置）
    # 企业可扩展此逻辑
    if user.roles:
        for role in user.roles:
            if role in allowed_roles:
                return user_id
    
    raise AppError(
        code=ErrorCode.PERMISSION_DENIED,
        message="admin app role is required",
        status_code=403,
    )


def verify_dify_bearer_token(request: Request, settings: Settings = Depends(get_settings_dep)) -> str:
    if not settings.dify_app_key:
        raise AppError(
            code=ErrorCode.DIFY_APP_KEY_MISSING,
            message="dify app key is not configured",
            status_code=400,
        )

    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.startswith("Bearer "):
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="missing dify bearer token",
            status_code=401,
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.dify_app_key:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="invalid dify bearer token",
            status_code=401,
        )

    return token


def _read_user_id_from_headers(request: Request, header_names: str) -> str | None:
    for header_name in [item.strip() for item in header_names.split(",") if item.strip()]:
        user_id = request.headers.get(header_name)
        if user_id and user_id.strip():
            return user_id.strip()
    return None


def _read_trusted_admin_context(request: Request, settings: Settings, session: Session) -> UserContext | None:
    user_id = _read_user_id_from_headers(
        request=request,
        header_names=settings.admin_auth_user_headers,
    )
    if user_id is not None:
        return UserContext(user_id=user_id, is_trusted_identity=True)

    if not settings.trusted_identity_header_enabled:
        return None

    external_source = _read_user_id_from_headers(
        request=request,
        header_names=settings.trusted_identity_external_source_headers,
    )
    external_id = _read_user_id_from_headers(
        request=request,
        header_names=settings.trusted_identity_external_id_headers,
    )
    if external_source is None or external_id is None:
        return None

    user = IdentityRepository(session).get_user_by_external_identity(
        external_source=external_source,
        external_id=external_id,
    )
    if user is None:
        return UserContext(
            user_id=f"external:{external_source}:{external_id}",
            is_trusted_identity=True,
            is_external_identity=True,
        )
    return UserContext(user_id=user.user_id, is_trusted_identity=True, is_external_identity=True)


def _read_user_id_from_session_token(request: Request, settings: Settings, session: Session) -> str | None:
    if not settings.auth_session_enabled:
        return None

    authorization = request.headers.get("Authorization", "").strip()
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="invalid authorization scheme",
            status_code=401,
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError(
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="session token is missing",
            status_code=401,
        )
    payload = verify_session_token(token, settings)
    if payload.token_id is not None:
        auth_session = session.scalar(select(AuthSession).where(AuthSession.token_id == payload.token_id))
        if auth_session is None:
            raise AppError(
                code=ErrorCode.AUTHENTICATION_FAILED,
                message="session token is not registered",
                status_code=401,
            )
        if auth_session.user_id != payload.user_id:
            raise AppError(
                code=ErrorCode.AUTHENTICATION_FAILED,
                message="session token subject mismatch",
                status_code=401,
            )
        if auth_session.revoked_at is not None:
            raise AppError(
                code=ErrorCode.AUTHENTICATION_FAILED,
                message="session token has been revoked",
                status_code=401,
            )
        if _to_utc(auth_session.expires_at) <= datetime.now(UTC):
            raise AppError(
                code=ErrorCode.AUTHENTICATION_FAILED,
                message="session token expired",
                status_code=401,
            )
    return payload.user_id


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
