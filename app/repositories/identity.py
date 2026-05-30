from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.identity import Department, Role, UserAccount, UserDepartment, UserRole


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_users(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[UserAccount], int]:
        stmt = select(UserAccount)
        count_stmt = select(func.count()).select_from(UserAccount)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                UserAccount.user_id.ilike(pattern) | UserAccount.display_name.ilike(pattern) | UserAccount.email.ilike(pattern)
            )
            count_stmt = count_stmt.where(
                UserAccount.user_id.ilike(pattern) | UserAccount.display_name.ilike(pattern) | UserAccount.email.ilike(pattern)
            )
        if status:
            stmt = stmt.where(UserAccount.status == status)
            count_stmt = count_stmt.where(UserAccount.status == status)
        stmt = stmt.order_by(UserAccount.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list(self.session.scalars(stmt)), self.session.scalar(count_stmt) or 0

    def get_user(self, user_id: str) -> UserAccount | None:
        return self.session.scalar(select(UserAccount).where(UserAccount.user_id == user_id))

    def get_user_by_external_identity(self, external_source: str, external_id: str) -> UserAccount | None:
        stmt = select(UserAccount).where(
            UserAccount.external_source == external_source,
            UserAccount.external_id == external_id,
        )
        return self.session.scalar(stmt)

    def get_user_by_external_identity_except(
        self,
        *,
        external_source: str,
        external_id: str,
        user_id: str,
    ) -> UserAccount | None:
        stmt = select(UserAccount).where(
            UserAccount.external_source == external_source,
            UserAccount.external_id == external_id,
            UserAccount.user_id != user_id,
        )
        return self.session.scalar(stmt)

    def list_users_by_external_source(self, external_source: str) -> list[UserAccount]:
        stmt = select(UserAccount).where(UserAccount.external_source == external_source).order_by(UserAccount.user_id)
        return list(self.session.scalars(stmt))

    def add_user(self, user: UserAccount) -> UserAccount:
        self.session.add(user)
        self.session.flush()
        return user

    def list_departments(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Department], int]:
        stmt = select(Department)
        count_stmt = select(func.count()).select_from(Department)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(Department.dept_code.ilike(pattern) | Department.dept_name.ilike(pattern))
            count_stmt = count_stmt.where(Department.dept_code.ilike(pattern) | Department.dept_name.ilike(pattern))
        if status:
            stmt = stmt.where(Department.status == status)
            count_stmt = count_stmt.where(Department.status == status)
        stmt = stmt.order_by(Department.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list(self.session.scalars(stmt)), self.session.scalar(count_stmt) or 0

    def get_department(self, dept_code: str) -> Department | None:
        return self.session.scalar(select(Department).where(Department.dept_code == dept_code))

    def add_department(self, department: Department) -> Department:
        self.session.add(department)
        self.session.flush()
        return department

    def list_roles(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Role], int]:
        stmt = select(Role)
        count_stmt = select(func.count()).select_from(Role)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(Role.role_code.ilike(pattern) | Role.role_name.ilike(pattern))
            count_stmt = count_stmt.where(Role.role_code.ilike(pattern) | Role.role_name.ilike(pattern))
        if status:
            stmt = stmt.where(Role.status == status)
            count_stmt = count_stmt.where(Role.status == status)
        stmt = stmt.order_by(Role.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list(self.session.scalars(stmt)), self.session.scalar(count_stmt) or 0

    def get_role(self, role_code: str) -> Role | None:
        return self.session.scalar(select(Role).where(Role.role_code == role_code))

    def add_role(self, role: Role) -> Role:
        self.session.add(role)
        self.session.flush()
        return role

    def set_user_departments(self, user_id: str, dept_codes: list[str], primary_dept_code: str | None = None) -> None:
        self.session.execute(delete(UserDepartment).where(UserDepartment.user_id == user_id))
        for dept_code in dept_codes:
            self.session.add(
                UserDepartment(
                    user_id=user_id,
                    dept_code=dept_code,
                    is_primary=bool(primary_dept_code and dept_code == primary_dept_code),
                )
            )

    def set_user_roles(self, user_id: str, role_codes: list[str]) -> None:
        self.session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for role_code in role_codes:
            self.session.add(UserRole(user_id=user_id, role_code=role_code))

    def get_user_departments(self, user_id: str) -> list[str]:
        stmt = select(UserDepartment.dept_code).where(UserDepartment.user_id == user_id).order_by(UserDepartment.is_primary.desc())
        return list(self.session.scalars(stmt))

    def get_user_roles(self, user_id: str) -> list[str]:
        stmt = select(UserRole.role_code).where(UserRole.user_id == user_id)
        return list(self.session.scalars(stmt))
