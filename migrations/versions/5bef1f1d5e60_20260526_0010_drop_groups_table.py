"""drop groups table
Revision ID: 5bef1f1d5e60
Revises: 20260525_0009
Create Date: 2026-05-26 15:27:54
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260526_0010"
down_revision: Union[str, None] = "20260525_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_groups_external_identity", table_name="groups")
    op.drop_index("idx_groups_type_status", table_name="groups")
    op.drop_index("uq_groups_group_code", table_name="groups")
    op.drop_index("uq_groups_group_uuid", table_name="groups")
    op.drop_table("groups")


def downgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_uuid", sa.Uuid(), nullable=False),
        sa.Column("group_code", sa.String(64), nullable=False),
        sa.Column("group_name", sa.String(128), nullable=False),
        sa.Column("group_type", sa.String(32), server_default="custom", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("external_source", sa.String(64), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("attributes_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_groups_group_uuid", "groups", ["group_uuid"], unique=True)
    op.create_index("uq_groups_group_code", "groups", ["group_code"], unique=True)
    op.create_index("idx_groups_type_status", "groups", ["group_type", "status"])
    op.create_index("idx_groups_external_identity", "groups", ["external_source", "external_id"])
