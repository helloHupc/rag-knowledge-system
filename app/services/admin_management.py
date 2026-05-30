from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.identity import Department, Role, UserAccount
from app.models.system_config import SystemConfig
from app.repositories.identity import IdentityRepository
from app.repositories.system_configs import SystemConfigRepository
from app.schemas.admin import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
    SystemConfigCreateRequest,
    SystemConfigResponse,
    SystemConfigUpdateRequest,
    UserCreateRequest,
    UserResponse,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.schemas.pagination import PaginatedResponse


USER_STATUSES = {"active", "inactive", "deleted"}
DEPARTMENT_STATUSES = {"active", "inactive"}
ROLE_STATUSES = {"active", "inactive"}


class AdminManagementService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.system_configs = SystemConfigRepository(session)
        self.identity = IdentityRepository(session)

    # ── System Configs ──────────────────────────────────────────

    def list_system_configs(self, *, page: int, page_size: int, keyword: str | None = None) -> PaginatedResponse[SystemConfigResponse]:
        items, total = self.system_configs.list_configs(page=page, page_size=page_size, keyword=keyword)
        return PaginatedResponse(
            items=[SystemConfigResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_system_config(self, config_id: int) -> SystemConfigResponse:
        config = self.system_configs.get_by_id(config_id)
        if config is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="system config not found", status_code=404)
        return SystemConfigResponse.model_validate(config)

    def create_system_config(self, request: SystemConfigCreateRequest) -> SystemConfigResponse:
        existing = self.system_configs.get_by_key(request.config_key)
        if existing is not None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="config_key already exists", status_code=409)
        config = SystemConfig(
            config_key=request.config_key,
            config_value=request.config_value,
            description=request.description,
        )
        self.session.add(config)
        self.session.commit()
        self.session.refresh(config)
        return SystemConfigResponse.model_validate(config)

    def update_system_config(self, config_id: int, request: SystemConfigUpdateRequest) -> SystemConfigResponse:
        config = self.system_configs.get_by_id(config_id)
        if config is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="system config not found", status_code=404)
        if request.config_value is not None:
            config.config_value = request.config_value
        if request.description is not None:
            config.description = request.description
        self.session.commit()
        self.session.refresh(config)
        return SystemConfigResponse.model_validate(config)

    # ── Departments ─────────────────────────────────────────────

    def list_departments(
        self, *, page: int, page_size: int, status: str | None = None
    ) -> PaginatedResponse[DepartmentResponse]:
        items, total = self.identity.list_departments(page=page, page_size=page_size, status=status)
        return PaginatedResponse(
            items=[DepartmentResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_department(self, dept_code: str) -> DepartmentResponse:
        dept = self.identity.get_department(dept_code)
        if dept is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="department not found", status_code=404)
        return DepartmentResponse.model_validate(dept)

    def create_department(self, request: DepartmentCreateRequest) -> DepartmentResponse:
        existing = self.identity.get_department(request.dept_code)
        if existing is not None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="dept_code already exists", status_code=409)
        dept = Department(
            dept_code=request.dept_code,
            dept_name=request.dept_name,
            parent_dept_code=request.parent_dept_code,
            status=request.status or "active",
        )
        self.session.add(dept)
        self.session.commit()
        self.session.refresh(dept)
        return DepartmentResponse.model_validate(dept)

    def update_department(self, dept_code: str, request: DepartmentUpdateRequest) -> DepartmentResponse:
        dept = self.identity.get_department(dept_code)
        if dept is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="department not found", status_code=404)
        if request.dept_name is not None:
            dept.dept_name = request.dept_name
        if request.parent_dept_code is not None:
            dept.parent_dept_code = request.parent_dept_code
        if request.status is not None:
            dept.status = request.status
        self.session.commit()
        self.session.refresh(dept)
        return DepartmentResponse.model_validate(dept)

    # ── Roles ───────────────────────────────────────────────────

    def list_roles(
        self, *, page: int, page_size: int, status: str | None = None
    ) -> PaginatedResponse[RoleResponse]:
        items, total = self.identity.list_roles(page=page, page_size=page_size, status=status)
        return PaginatedResponse(
            items=[RoleResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_role(self, role_code: str) -> RoleResponse:
        role = self.identity.get_role(role_code)
        if role is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="role not found", status_code=404)
        return RoleResponse.model_validate(role)

    def create_role(self, request: RoleCreateRequest) -> RoleResponse:
        existing = self.identity.get_role(request.role_code)
        if existing is not None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="role_code already exists", status_code=409)
        role = Role(
            role_code=request.role_code,
            role_name=request.role_name,
            description=request.description,
            status=request.status or "active",
        )
        self.session.add(role)
        self.session.commit()
        self.session.refresh(role)
        return RoleResponse.model_validate(role)

    def update_role(self, role_code: str, request: RoleUpdateRequest) -> RoleResponse:
        role = self.identity.get_role(role_code)
        if role is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="role not found", status_code=404)
        if request.role_name is not None:
            role.role_name = request.role_name
        if request.description is not None:
            role.description = request.description
        if request.status is not None:
            role.status = request.status
        self.session.commit()
        self.session.refresh(role)
        return RoleResponse.model_validate(role)

    # ── Users ───────────────────────────────────────────────────

    def list_users(
        self, *, page: int, page_size: int, keyword: str | None = None, status: str | None = None
    ) -> PaginatedResponse[UserResponse]:
        items, total = self.identity.list_users(page=page, page_size=page_size, keyword=keyword, status=status)
        return PaginatedResponse(
            items=[self._build_user_response(user) for user in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_user(self, user_id: str) -> UserResponse:
        user = self.identity.get_user(user_id)
        if user is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="user not found", status_code=404)
        return self._build_user_response(user)

    def create_user(self, request: UserCreateRequest) -> UserResponse:
        if not self.settings.admin_manual_user_creation_enabled:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="manual user creation is disabled",
                status_code=403,
            )
        existing = self.identity.get_user(request.user_id)
        if existing is not None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="user_id already exists", status_code=409)
        user = UserAccount(
            user_id=request.user_id,
            display_name=request.display_name,
            email=request.email,
            employee_no=request.employee_no,
            status=request.status or "active",
            external_source=request.external_source,
            external_id=request.external_id,
            extra_meta=request.extra_meta or {},
        )
        self.session.add(user)
        self.session.flush()
        # Set department associations
        if request.department_codes:
            self.identity.set_user_departments(
                request.user_id,
                request.department_codes,
                primary_dept_code=request.primary_dept_code,
            )
        # Set role associations
        if request.role_codes:
            self.identity.set_user_roles(request.user_id, request.role_codes)
        self.session.commit()
        self.session.refresh(user)
        return self._build_user_response(user)

    def update_user(self, user_id: str, request: UserUpdateRequest) -> UserResponse:
        user = self.identity.get_user(user_id)
        if user is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="user not found", status_code=404)
        if request.display_name is not None:
            user.display_name = request.display_name
        if request.email is not None:
            user.email = request.email
        if request.status is not None:
            user.status = request.status
        # Update department associations
        if request.department_codes is not None:
            self.identity.set_user_departments(
                user_id,
                request.department_codes,
                primary_dept_code=request.primary_dept_code,
            )
        # Update role associations
        if request.role_codes is not None:
            self.identity.set_user_roles(user_id, request.role_codes)
        self.session.commit()
        self.session.refresh(user)
        return self._build_user_response(user)

    def update_user_status(self, user_id: str, request: UserStatusUpdateRequest) -> UserResponse:
        user = self.identity.get_user(user_id)
        if user is None:
            raise AppError(code=ErrorCode.INVALID_REQUEST, message="user not found", status_code=404)
        status = self._validate_status(request.status, USER_STATUSES, "status")
        user.status = status
        self.session.commit()
        self.session.refresh(user)
        return self._build_user_response(user)

    def _build_user_response(self, user: UserAccount) -> UserResponse:
        departments = self.identity.get_user_departments(user.user_id)
        roles = self.identity.get_user_roles(user.user_id)
        return UserResponse(
            id=user.id,
            user_uuid=user.user_uuid,
            user_id=user.user_id,
            display_name=user.display_name,
            email=user.email,
            employee_no=user.employee_no,
            status=user.status,
            department_codes=departments,
            role_codes=roles,
            external_source=user.external_source,
            external_id=user.external_id,
            extra_meta=user.extra_meta or {},
            created_by=user.created_by,
            updated_by=user.updated_by,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def _validate_status(status: str, allowed: set[str], field_name: str) -> str:
        normalized = status.strip().lower()
        if normalized not in allowed:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"{field_name} must be one of {sorted(allowed)}",
                status_code=422,
            )
        return normalized
