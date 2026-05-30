"""unique user external identity

Revision ID: 20260525_0008
Revises: 20260525_0007
Create Date: 2026-05-25 22:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260525_0008"
down_revision = "20260525_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_users_external_identity", table_name="users")
    op.create_index(
        "uq_users_external_identity",
        "users",
        ["external_source", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_external_identity", table_name="users")
    op.create_index(
        "idx_users_external_identity",
        "users",
        ["external_source", "external_id"],
        unique=False,
    )
