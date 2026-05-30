from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import AppBaseModel


class SystemConfigCreateRequest(AppBaseModel):
    config_key: str
    config_value: dict
    description: str | None = None


class SystemConfigUpdateRequest(AppBaseModel):
    config_value: dict | None = None
    description: str | None = None


class SystemConfigResponse(AppBaseModel):
    id: int
    config_key: str
    config_value: dict
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class AccessPolicyCreateRequest(AppBaseModel):
    resource_type: str
    resource_id: str
    effect_scope: str = "allow"
    role_codes: list[str] = []
    dept_codes: list[str] = []
    user_ids: list[str] = []
    extra_rules: dict = {}
    created_by: str | None = None


class AccessPolicyUpdateRequest(AppBaseModel):
    effect_scope: str | None = None
    role_codes: list[str] | None = None
    dept_codes: list[str] | None = None
    user_ids: list[str] | None = None
    extra_rules: dict | None = None
    created_by: str | None = None


class AccessPolicyResponse(AppBaseModel):
    id: int
    policy_uuid: UUID
    resource_type: str
    resource_id: str
    effect_scope: str
    role_codes: list
    dept_codes: list
    user_ids: list
    extra_rules: dict
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class AccessPolicyMigrationRequest(AppBaseModel):
    dry_run: bool = False
    created_by: str | None = None


class AccessPolicyMigrationItem(AppBaseModel):
    access_policy_id: int
    resource_type: str
    resource_id: str
    effect: str
    principal_type: str | None = None
    principal_id: str | None = None
    status: str
    message: str | None = None
    resource_permission_id: int | None = None
    resource_permission_uuid: UUID | None = None


class AccessPolicyMigrationResponse(AppBaseModel):
    dry_run: bool
    total_policies: int
    created_count: int
    skipped_count: int
    failed_count: int
    items: list[AccessPolicyMigrationItem]


class DepartmentCreateRequest(AppBaseModel):
    dept_code: str
    dept_name: str
    parent_dept_code: str | None = None
    status: str = "active"
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict = {}


class DepartmentUpdateRequest(AppBaseModel):
    dept_name: str | None = None
    parent_dept_code: str | None = None
    status: str | None = None
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict | None = None


class DepartmentResponse(AppBaseModel):
    id: int
    dept_uuid: UUID
    dept_code: str
    dept_name: str
    parent_dept_code: str | None = None
    status: str
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict
    created_at: datetime
    updated_at: datetime


class RoleCreateRequest(AppBaseModel):
    role_code: str
    role_name: str
    description: str | None = None
    status: str = "active"
    permissions: list[str] = []
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict = {}


class RoleUpdateRequest(AppBaseModel):
    role_name: str | None = None
    description: str | None = None
    status: str | None = None
    permissions: list[str] | None = None
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict | None = None


class RoleResponse(AppBaseModel):
    id: int
    role_uuid: UUID
    role_code: str
    role_name: str
    description: str | None = None
    status: str
    permissions: list
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict
    created_at: datetime
    updated_at: datetime


class UserCreateRequest(AppBaseModel):
    user_id: str
    display_name: str
    email: str | None = None
    employee_no: str | None = None
    status: str = "active"
    department_codes: list[str] = []
    role_codes: list[str] = []
    primary_dept_code: str | None = None
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict = {}
    created_by: str | None = None


class UserUpdateRequest(AppBaseModel):
    display_name: str | None = None
    email: str | None = None
    employee_no: str | None = None
    status: str | None = None
    department_codes: list[str] | None = None
    role_codes: list[str] | None = None
    primary_dept_code: str | None = None
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict | None = None
    updated_by: str | None = None


class UserStatusUpdateRequest(AppBaseModel):
    status: str
    updated_by: str | None = None


class UserResponse(AppBaseModel):
    id: int
    user_uuid: UUID
    user_id: str
    display_name: str
    email: str | None = None
    employee_no: str | None = None
    status: str
    department_codes: list[str]
    role_codes: list[str]
    external_source: str | None = None
    external_id: str | None = None
    extra_meta: dict
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime
