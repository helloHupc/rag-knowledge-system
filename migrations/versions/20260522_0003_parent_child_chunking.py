"""parent-child chunking columns

Revision ID: 20260522_0003
Revises: 20260522_0002
Create Date: 2026-05-22 08:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260522_0003"
down_revision = "20260522_0002"
branch_labels = None
depends_on = None


def _uuid_type(dialect_name: str):
    if dialect_name == "postgresql":
        return postgresql.UUID(as_uuid=False)
    return sa.String(length=36)


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    uuid_type = _uuid_type(dialect_name)

    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.add_column(
            sa.Column("parent_chunk_uuid", uuid_type, nullable=True)
        )
        batch_op.add_column(
            sa.Column("chunk_group_uuid", uuid_type, nullable=True)
        )
        batch_op.add_column(
            sa.Column("chunk_level", sa.String(length=16), nullable=True)
        )
        batch_op.add_column(
            sa.Column("context_text", sa.Text(), nullable=True)
        )

    op.create_index(
        "idx_document_chunks_parent_chunk_uuid",
        "document_chunks",
        ["parent_chunk_uuid"],
        unique=False,
    )
    op.create_index(
        "idx_document_chunks_chunk_group_uuid",
        "document_chunks",
        ["chunk_group_uuid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_document_chunks_chunk_group_uuid", table_name="document_chunks")
    op.drop_index("idx_document_chunks_parent_chunk_uuid", table_name="document_chunks")

    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.drop_column("context_text")
        batch_op.drop_column("chunk_level")
        batch_op.drop_column("chunk_group_uuid")
        batch_op.drop_column("parent_chunk_uuid")
