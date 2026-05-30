"""identity permission architecture

Revision ID: 20260525_0005
Revises: 20260525_0004
Create Date: 2026-05-25 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0005"
down_revision = "20260525_0004"
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
        "identity_sources",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("source_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("config_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("field_mapping_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("sync_mode", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_identity_sources_source_uuid", "identity_sources", ["source_uuid"], unique=True)
    op.create_index("uq_identity_sources_source_id", "identity_sources", ["source_id"], unique=True)
    op.create_index("idx_identity_sources_type_status", "identity_sources", ["source_type", "status"])

    op.create_table(
        "groups",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("group_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("group_code", sa.String(length=64), nullable=False),
        sa.Column("group_name", sa.String(length=128), nullable=False),
        sa.Column("group_type", sa.String(length=32), nullable=False, server_default="custom"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("external_source", sa.String(length=64)),
        sa.Column("external_id", sa.String(length=128)),
        sa.Column("attributes_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_groups_group_uuid", "groups", ["group_uuid"], unique=True)
    op.create_index("uq_groups_group_code", "groups", ["group_code"], unique=True)
    op.create_index("idx_groups_type_status", "groups", ["group_type", "status"])
    op.create_index("idx_groups_external_identity", "groups", ["external_source", "external_id"])

    op.create_table(
        "user_memberships",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=false_default),
        sa.Column("external_source", sa.String(length=64)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_user_memberships_user_principal",
        "user_memberships",
        ["user_id", "principal_type", "principal_id"],
        unique=True,
    )
    op.create_index("idx_user_memberships_principal", "user_memberships", ["principal_type", "principal_id"])
    op.create_index("idx_user_memberships_external_source", "user_memberships", ["external_source"])

    op.create_table(
        "app_roles",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("role_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("role_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("permissions", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_app_roles_role_uuid", "app_roles", ["role_uuid"], unique=True)
    op.create_index("uq_app_roles_role_code", "app_roles", ["role_code"], unique=True)
    op.create_index("idx_app_roles_status", "app_roles", ["status"])

    op.create_table(
        "user_app_roles",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
    )
    op.create_index("uq_user_app_roles_user_role", "user_app_roles", ["user_id", "role_code"], unique=True)
    op.create_index("idx_user_app_roles_role_code", "user_app_roles", ["role_code"])

    op.create_table(
        "resource_permissions",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("permission_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="read"),
        sa.Column("effect", sa.String(length=32), nullable=False, server_default="allow"),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("condition_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_resource_permissions_permission_uuid", "resource_permissions", ["permission_uuid"], unique=True)
    op.create_index("idx_resource_permissions_resource", "resource_permissions", ["resource_type", "resource_id"])
    op.create_index("idx_resource_permissions_principal", "resource_permissions", ["principal_type", "principal_id"])
    op.create_index("idx_resource_permissions_action_effect", "resource_permissions", ["action", "effect"])


def downgrade() -> None:
    op.drop_index("idx_resource_permissions_action_effect", table_name="resource_permissions")
    op.drop_index("idx_resource_permissions_principal", table_name="resource_permissions")
    op.drop_index("idx_resource_permissions_resource", table_name="resource_permissions")
    op.drop_index("uq_resource_permissions_permission_uuid", table_name="resource_permissions")
    op.drop_table("resource_permissions")

    op.drop_index("idx_user_app_roles_role_code", table_name="user_app_roles")
    op.drop_index("uq_user_app_roles_user_role", table_name="user_app_roles")
    op.drop_table("user_app_roles")

    op.drop_index("idx_app_roles_status", table_name="app_roles")
    op.drop_index("uq_app_roles_role_code", table_name="app_roles")
    op.drop_index("uq_app_roles_role_uuid", table_name="app_roles")
    op.drop_table("app_roles")

    op.drop_index("idx_user_memberships_external_source", table_name="user_memberships")
    op.drop_index("idx_user_memberships_principal", table_name="user_memberships")
    op.drop_index("uq_user_memberships_user_principal", table_name="user_memberships")
    op.drop_table("user_memberships")

    op.drop_index("idx_groups_external_identity", table_name="groups")
    op.drop_index("idx_groups_type_status", table_name="groups")
    op.drop_index("uq_groups_group_code", table_name="groups")
    op.drop_index("uq_groups_group_uuid", table_name="groups")
    op.drop_table("groups")

    op.drop_index("idx_identity_sources_type_status", table_name="identity_sources")
    op.drop_index("uq_identity_sources_source_id", table_name="identity_sources")
    op.drop_index("uq_identity_sources_source_uuid", table_name="identity_sources")
    op.drop_table("identity_sources")
