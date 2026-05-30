from __future__ import annotations

from app.schemas.common import AppBaseModel
from app.schemas.retrieval import UserContext


class SessionTokenResponse(AppBaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_context: UserContext


class LogoutResponse(AppBaseModel):
    user_id: str
    revoked: bool


class CurrentUserResponse(AppBaseModel):
    user_uuid: str
    user_id: str
    display_name: str
    email: str | None = None
    employee_no: str | None = None
    status: str
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict
    user_context: UserContext
