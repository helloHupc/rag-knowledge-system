"""identity and access context

Revision ID: 20260525_0004
Revises: 20260522_0003
Create Date: 2026-05-25 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0004"
down_revision = "20260522_0003"
branch_labels = None
depends_on = None


def _json_type(dialect_name: str):
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _uuid_type(dialect_name: str):
    if dialect_name == "postgresql":
        return postgresql.UUID(as_uuid=False)
    return sa.String(length=36)


def _pk_type(dialect_name: str):
    if dialect_name == "sqlite":
        return sa.Integer()
    return sa.BigInteger()


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    json_type = _json_type(dialect_name)
    uuid_type = _uuid_type(dialect_name)
    pk_type = _pk_type(dialect_name)

    server_uuid = sa.text("gen_random_uuid()") if dialect_name == "postgresql" else None
    server_now = sa.text("CURRENT_TIMESTAMP")
    json_empty_array = sa.text("'[]'::jsonb") if dialect_name == "postgresql" else sa.text("'[]'")
    json_empty_object = sa.text("'{}'::jsonb") if dialect_name == "postgresql" else sa.text("'{}'")
    false_default = sa.text("false") if dialect_name == "postgresql" else sa.text("0")

    op.create_table(
        "users",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("user_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255)),
        sa.Column("employee_no", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("external_source", sa.String(length=64)),
        sa.Column("external_id", sa.String(length=128)),
        sa.Column("extra_meta", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("updated_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_users_user_uuid", "users", ["user_uuid"], unique=True)
    op.create_index("uq_users_user_id", "users", ["user_id"], unique=True)
    op.create_index("idx_users_status", "users", ["status"], unique=False)
    op.create_index("idx_users_external_identity", "users", ["external_source", "external_id"], unique=False)

    op.create_table(
        "departments",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("dept_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("dept_code", sa.String(length=64), nullable=False),
        sa.Column("dept_name", sa.String(length=128), nullable=False),
        sa.Column("parent_dept_code", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("external_source", sa.String(length=64)),
        sa.Column("external_id", sa.String(length=128)),
        sa.Column("extra_meta", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_departments_dept_uuid", "departments", ["dept_uuid"], unique=True)
    op.create_index("uq_departments_dept_code", "departments", ["dept_code"], unique=True)
    op.create_index("idx_departments_parent_dept_code", "departments", ["parent_dept_code"], unique=False)
    op.create_index("idx_departments_external_identity", "departments", ["external_source", "external_id"], unique=False)

    op.create_table(
        "roles",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("role_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("role_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("permissions", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("external_source", sa.String(length=64)),
        sa.Column("external_id", sa.String(length=128)),
        sa.Column("extra_meta", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_roles_role_uuid", "roles", ["role_uuid"], unique=True)
    op.create_index("uq_roles_role_code", "roles", ["role_code"], unique=True)
    op.create_index("idx_roles_external_identity", "roles", ["external_source", "external_id"], unique=False)

    op.create_table(
        "user_departments",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("dept_code", sa.String(length=64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=false_default),
    )
    op.create_index("uq_user_departments_user_dept", "user_departments", ["user_id", "dept_code"], unique=True)
    op.create_index("idx_user_departments_dept_code", "user_departments", ["dept_code"], unique=False)

    op.create_table(
        "user_roles",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
    )
    op.create_index("uq_user_roles_user_role", "user_roles", ["user_id", "role_code"], unique=True)
    op.create_index("idx_user_roles_role_code", "user_roles", ["role_code"], unique=False)

    if dialect_name == "postgresql":
        op.execute("CREATE INDEX idx_roles_permissions ON roles USING GIN(permissions);")


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.drop_index("idx_roles_permissions", table_name="roles")

    op.drop_index("idx_user_roles_role_code", table_name="user_roles")
    op.drop_index("uq_user_roles_user_role", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("idx_user_departments_dept_code", table_name="user_departments")
    op.drop_index("uq_user_departments_user_dept", table_name="user_departments")
    op.drop_table("user_departments")

    op.drop_index("idx_roles_external_identity", table_name="roles")
    op.drop_index("uq_roles_role_code", table_name="roles")
    op.drop_index("uq_roles_role_uuid", table_name="roles")
    op.drop_table("roles")

    op.drop_index("idx_departments_external_identity", table_name="departments")
    op.drop_index("idx_departments_parent_dept_code", table_name="departments")
    op.drop_index("uq_departments_dept_code", table_name="departments")
    op.drop_index("uq_departments_dept_uuid", table_name="departments")
    op.drop_table("departments")

    op.drop_index("idx_users_external_identity", table_name="users")
    op.drop_index("idx_users_status", table_name="users")
    op.drop_index("uq_users_user_id", table_name="users")
    op.drop_index("uq_users_user_uuid", table_name="users")
    op.drop_table("users")
