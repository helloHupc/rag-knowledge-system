from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.identity import UserAccount
from app.repositories.identity import IdentityRepository
from app.schemas.retrieval import UserContext


class IdentityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.identity = IdentityRepository(session)

    def resolve_user_context(self, user_context: UserContext) -> UserContext:
        user = self.identity.get_user(user_context.user_id)
        if user is None and self._can_jit_create_user(user_context):
            user = self._jit_create_user(user_context.user_id)

        if user is None or user.status != "active":
            return UserContext(
                user_id=user_context.user_id,
                roles=[],
                departments=[],
                is_super_admin=False,
                is_trusted_identity=user_context.is_trusted_identity,
                is_session_identity=user_context.is_session_identity,
                is_external_identity=user_context.is_external_identity,
            )

        roles = self.identity.get_user_roles(user.user_id)
        departments = self.identity.get_user_departments(user.user_id)
        extra_meta = user.extra_meta or {}
        return UserContext(
            user_id=user.user_id,
            roles=roles,
            departments=departments,
            is_super_admin=False,
            is_authenticated=True,
            is_trusted_identity=user_context.is_trusted_identity,
            is_session_identity=user_context.is_session_identity,
            is_external_identity=user_context.is_external_identity,
            is_jit_user=bool(extra_meta.get("created_by_jit")),
        )

    def _can_jit_create_user(self, user_context: UserContext) -> bool:
        return bool(
            user_context.is_trusted_identity
            and not user_context.is_session_identity
            and not user_context.is_external_identity
            and self.settings.trusted_identity_header_enabled
            and self.settings.trusted_identity_jit_enabled
        )

    def _jit_create_user(self, user_id: str) -> UserAccount:
        existing = self.identity.get_user_by_external_identity_except(
            external_source=self.settings.trusted_identity_jit_source_id,
            external_id=user_id,
            user_id=user_id,
        )
        if existing is not None:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="external identity already maps to another user",
                status_code=409,
            )
        user = UserAccount(
            user_id=user_id,
            display_name=user_id,
            status="active",
            external_source=self.settings.trusted_identity_jit_source_id,
            external_id=user_id,
            extra_meta={"created_by_jit": True, "jit_source": "trusted_identity_header"},
            created_by=f"jit:{self.settings.trusted_identity_jit_source_id}",
        )
        self.identity.add_user(user)
        self.session.commit()
        self.session.refresh(user)
        return user
