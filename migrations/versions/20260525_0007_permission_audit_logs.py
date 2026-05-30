"""permission audit logs

Revision ID: 20260525_0007
Revises: 20260525_0006
Create Date: 2026-05-25 20:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0007"
down_revision = "20260525_0006"
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

    op.create_table(
        "permission_audit_logs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("audit_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64)),
        sa.Column("before_json", json_type),
        sa.Column("after_json", json_type),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("idx_permission_audit_logs_target", "permission_audit_logs", ["target_type", "target_id"])
    op.create_index("idx_permission_audit_logs_action", "permission_audit_logs", ["action"])
    op.create_index("idx_permission_audit_logs_actor", "permission_audit_logs", ["actor_id"])
    op.create_index("idx_permission_audit_logs_created_at", "permission_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_permission_audit_logs_created_at", table_name="permission_audit_logs")
    op.drop_index("idx_permission_audit_logs_actor", table_name="permission_audit_logs")
    op.drop_index("idx_permission_audit_logs_action", table_name="permission_audit_logs")
    op.drop_index("idx_permission_audit_logs_target", table_name="permission_audit_logs")
    op.drop_table("permission_audit_logs")
