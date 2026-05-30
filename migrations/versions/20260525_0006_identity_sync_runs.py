"""identity sync runs

Revision ID: 20260525_0006
Revises: 20260525_0005
Create Date: 2026-05-25 19:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0006"
down_revision = "20260525_0005"
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
        "identity_sync_runs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("run_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_identity_sync_runs_run_uuid", "identity_sync_runs", ["run_uuid"], unique=True)
    op.create_index("idx_identity_sync_runs_source_id", "identity_sync_runs", ["source_id"])
    op.create_index("idx_identity_sync_runs_status", "identity_sync_runs", ["status"])

    op.create_table(
        "identity_sync_items",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("run_uuid", uuid_type, nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("external_object_type", sa.String(length=32), nullable=False),
        sa.Column("external_object_id", sa.String(length=128), nullable=False),
        sa.Column("local_object_type", sa.String(length=32)),
        sa.Column("local_object_id", sa.String(length=128)),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("raw_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("idx_identity_sync_items_run_uuid", "identity_sync_items", ["run_uuid"])
    op.create_index(
        "idx_identity_sync_items_external_object",
        "identity_sync_items",
        ["external_object_type", "external_object_id"],
    )
    op.create_index("idx_identity_sync_items_status", "identity_sync_items", ["status"])


def downgrade() -> None:
    op.drop_index("idx_identity_sync_items_status", table_name="identity_sync_items")
    op.drop_index("idx_identity_sync_items_external_object", table_name="identity_sync_items")
    op.drop_index("idx_identity_sync_items_run_uuid", table_name="identity_sync_items")
    op.drop_table("identity_sync_items")

    op.drop_index("idx_identity_sync_runs_status", table_name="identity_sync_runs")
    op.drop_index("idx_identity_sync_runs_source_id", table_name="identity_sync_runs")
    op.drop_index("uq_identity_sync_runs_run_uuid", table_name="identity_sync_runs")
    op.drop_table("identity_sync_runs")
