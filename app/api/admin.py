from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_trace_id, require_admin_actor
from app.core.responses import success_response
from app.schemas.admin import (
    AccessPolicyCreateRequest,
    AccessPolicyMigrationRequest,
    AccessPolicyUpdateRequest,
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    RoleCreateRequest,
    RoleUpdateRequest,
    SystemConfigCreateRequest,
    SystemConfigUpdateRequest,
    UserCreateRequest,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.services.admin_management import AdminManagementService


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_actor)])


@router.get("/system-configs", response_model=dict)
def list_system_configs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).list_system_configs(page=page, page_size=page_size, keyword=keyword)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/system-configs/{config_id}", response_model=dict)
def get_system_config(
    config_id: int,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).get_system_config(config_id)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/system-configs", response_model=dict)
def create_system_config(
    request: SystemConfigCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).create_system_config(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/system-configs/{config_id}", response_model=dict)
def update_system_config(
    config_id: int,
    request: SystemConfigUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).update_system_config(config_id, request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/access-policies", response_model=dict)
def list_access_policies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).list_access_policies(
        page=page,
        page_size=page_size,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/access-policies/migrate-to-resource-permissions", response_model=dict)
def migrate_access_policies_to_resource_permissions(
    request: AccessPolicyMigrationRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    admin_actor_id: str | None = Depends(require_admin_actor),
):
    data = AdminManagementService(session).migrate_access_policies_to_resource_permissions(
        request,
        actor_id=admin_actor_id,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/access-policies/{policy_id}", response_model=dict)
def get_access_policy(
    policy_id: int,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).get_access_policy(policy_id)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/access-policies", response_model=dict)
def create_access_policy(
    request: AccessPolicyCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).create_access_policy(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/access-policies/{policy_id}", response_model=dict)
def update_access_policy(
    policy_id: int,
    request: AccessPolicyUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).update_access_policy(policy_id, request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.delete("/access-policies/{policy_id}", response_model=dict)
def delete_access_policy(
    policy_id: int,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    AdminManagementService(session).delete_access_policy(policy_id)
    return success_response({"policy_id": policy_id, "deleted": True}, trace_id)


@router.get("/departments", response_model=dict)
def list_departments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).list_departments(
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/departments/{dept_code}", response_model=dict)
def get_department(
    dept_code: str,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).get_department(dept_code)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/departments", response_model=dict)
def create_department(
    request: DepartmentCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).create_department(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/departments/{dept_code}", response_model=dict)
def update_department(
    dept_code: str,
    request: DepartmentUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).update_department(dept_code, request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/roles", response_model=dict)
def list_roles(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).list_roles(
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/roles/{role_code}", response_model=dict)
def get_role(
    role_code: str,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).get_role(role_code)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/roles", response_model=dict)
def create_role(
    request: RoleCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).create_role(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/roles/{role_code}", response_model=dict)
def update_role(
    role_code: str,
    request: RoleUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).update_role(role_code, request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/users", response_model=dict)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).list_users(
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/users/{user_id}", response_model=dict)
def get_user(
    user_id: str,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).get_user(user_id)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/users/{user_id}/status", response_model=dict)
def update_user_status(
    user_id: str,
    request: UserStatusUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    admin_actor_id: str | None = Depends(require_admin_actor),
):
    data = AdminManagementService(session).update_user_status(
        user_id,
        request,
        actor_id=admin_actor_id,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/users", response_model=dict)
def create_user(
    request: UserCreateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).create_user(request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/users/{user_id}", response_model=dict)
def update_user(
    user_id: str,
    request: UserUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = AdminManagementService(session).update_user(user_id, request)
    return success_response(data.model_dump(mode="json"), trace_id)
