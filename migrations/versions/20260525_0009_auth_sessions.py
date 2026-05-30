"""auth sessions

Revision ID: 20260525_0009
Revises: 20260525_0008
Create Date: 2026-05-25 23:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_0009"
down_revision = "20260525_0008"
branch_labels = None
depends_on = None


def _pk_type(dialect_name: str):
    if dialect_name == "sqlite":
        return sa.Integer()
    return sa.BigInteger()


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    pk_type = _pk_type(dialect_name)
    server_now = sa.text("CURRENT_TIMESTAMP")

    op.create_table(
        "auth_sessions",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("token_id", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("auth_method", sa.String(length=32), nullable=False),
        sa.Column("external_source", sa.String(length=64)),
        sa.Column("external_id", sa.String(length=128)),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=256)),
        sa.Column("client_ip", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_auth_sessions_token_id", "auth_sessions", ["token_id"], unique=True)
    op.create_index("idx_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("idx_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("idx_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"])


def downgrade() -> None:
    op.drop_index("idx_auth_sessions_revoked_at", table_name="auth_sessions")
    op.drop_index("idx_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("idx_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("uq_auth_sessions_token_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
