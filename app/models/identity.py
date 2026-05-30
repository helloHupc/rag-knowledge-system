from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt, UuidType
from app.models.mixins import TimestampMixin


class UserAccount(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_user_uuid", "user_uuid", unique=True),
        Index("uq_users_user_id", "user_id", unique=True),
        Index("idx_users_status", "status"),
        Index("uq_users_external_identity", "external_source", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    user_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    employee_no: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    external_source: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(128))
    extra_meta: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    created_by: Mapped[str | None] = mapped_column(String(64))
    updated_by: Mapped[str | None] = mapped_column(String(64))


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        Index("uq_departments_dept_uuid", "dept_uuid", unique=True),
        Index("uq_departments_dept_code", "dept_code", unique=True),
        Index("idx_departments_parent_dept_code", "parent_dept_code"),
        Index("idx_departments_external_identity", "external_source", "external_id"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    dept_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    dept_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dept_name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_dept_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    external_source: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(128))
    extra_meta: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index("uq_roles_role_uuid", "role_uuid", unique=True),
        Index("uq_roles_role_code", "role_code", unique=True),
        Index("idx_roles_external_identity", "external_source", "external_id"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    role_uuid: Mapped[uuid.UUID] = mapped_column(UuidType, default=uuid.uuid4, nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    role_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    permissions: Mapped[list] = mapped_column(JsonType, nullable=False, default=list, server_default="[]")
    external_source: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(128))
    extra_meta: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")


class UserDepartment(Base):
    __tablename__ = "user_departments"
    __table_args__ = (
        Index("uq_user_departments_user_dept", "user_id", "dept_code", unique=True),
        Index("idx_user_departments_dept_code", "dept_code"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dept_code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("uq_user_roles_user_role", "user_id", "role_code", unique=True),
        Index("idx_user_roles_role_code", "role_code"),
    )

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
