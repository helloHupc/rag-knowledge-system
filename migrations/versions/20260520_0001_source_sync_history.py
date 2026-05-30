"""source sync history

Revision ID: 20260520_0001
Revises: 20260519_0001
Create Date: 2026-05-20 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260520_0001"
down_revision = "20260519_0001"
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
    json_empty_object = sa.text("'{}'::jsonb") if dialect_name == "postgresql" else sa.text("'{}'")

    op.create_table(
        "source_sync_runs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("run_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("folder_path", sa.Text()),
        sa.Column("recursive", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("max_files", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("summary_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_source_sync_runs_run_uuid", "source_sync_runs", ["run_uuid"], unique=True)
    op.create_index("idx_source_sync_runs_source_type", "source_sync_runs", ["source_type"], unique=False)
    op.create_index("idx_source_sync_runs_status", "source_sync_runs", ["status"], unique=False)
    op.create_index("idx_source_sync_runs_created_at", "source_sync_runs", ["created_at"], unique=False)

    op.create_table(
        "source_sync_items",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("run_uuid", uuid_type, sa.ForeignKey("source_sync_runs.run_uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.Text()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text()),
        sa.Column("doc_uuid", uuid_type),
        sa.Column("job_uuid", uuid_type),
        sa.Column("chunk_count", sa.Integer()),
        sa.Column("metadata_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("idx_source_sync_items_run_uuid", "source_sync_items", ["run_uuid"], unique=False)
    op.create_index("idx_source_sync_items_status", "source_sync_items", ["status"], unique=False)
    op.create_index("idx_source_sync_items_doc_uuid", "source_sync_items", ["doc_uuid"], unique=False)


def downgrade() -> None:
    op.drop_table("source_sync_items")
    op.drop_table("source_sync_runs")
