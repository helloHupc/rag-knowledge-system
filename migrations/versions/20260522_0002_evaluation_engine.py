"""evaluation engine tables

Revision ID: 20260522_0002
Revises: 20260520_0001
Create Date: 2026-05-22 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260522_0002"
down_revision = "20260520_0001"
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
    json_empty_array = sa.text("'[]'::jsonb") if dialect_name == "postgresql" else sa.text("'[]'")

    # ── evaluation_datasets ──────────────────────────────────────
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("dataset_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_evaluation_datasets_dataset_uuid", "evaluation_datasets", ["dataset_uuid"], unique=True)

    # ── evaluation_queries ──────────────────────────────────────
    op.create_table(
        "evaluation_queries",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("query_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("dataset_uuid", uuid_type, sa.ForeignKey("evaluation_datasets.dataset_uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("expected_doc_titles", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("expected_terms", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("notes", sa.Text()),
    )
    op.create_index("uq_evaluation_queries_query_uuid", "evaluation_queries", ["query_uuid"], unique=True)
    op.create_index("idx_evaluation_queries_dataset_uuid", "evaluation_queries", ["dataset_uuid"], unique=False)

    # ── evaluation_chunks (isolated, same structure as document_chunks + run_uuid) ──
    op.create_table(
        "evaluation_chunks",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("chunk_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("run_uuid", uuid_type, nullable=False),
        sa.Column("doc_uuid", uuid_type, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("section_title", sa.String(length=255)),
        sa.Column("page_no", sa.Integer()),
        sa.Column("sheet_name", sa.String(length=255)),
        sa.Column("row_start", sa.Integer()),
        sa.Column("row_end", sa.Integer()),
        sa.Column("token_count", sa.Integer()),
        sa.Column("char_count", sa.Integer()),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_summary", sa.Text()),
        sa.Column("vector_id", sa.String(length=128)),
        sa.Column("zilliz_collection", sa.String(length=128)),
        sa.Column("metadata_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_evaluation_chunks_chunk_uuid", "evaluation_chunks", ["chunk_uuid"], unique=True)
    op.create_index("idx_evaluation_chunks_run_uuid", "evaluation_chunks", ["run_uuid"], unique=False)
    op.create_index("idx_evaluation_chunks_doc_uuid", "evaluation_chunks", ["doc_uuid"], unique=False)

    # ── evaluation_runs ──────────────────────────────────────────
    op.create_table(
        "evaluation_runs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("run_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("dataset_uuid", uuid_type, sa.ForeignKey("evaluation_datasets.dataset_uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("chunking_strategy", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("chunking_params", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("retrieval_strategy", sa.String(length=64), nullable=False, server_default="dense"),
        sa.Column("retrieval_params", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_evaluation_runs_run_uuid", "evaluation_runs", ["run_uuid"], unique=True)
    op.create_index("idx_evaluation_runs_dataset_uuid", "evaluation_runs", ["dataset_uuid"], unique=False)
    op.create_index("idx_evaluation_runs_status", "evaluation_runs", ["status"], unique=False)

    # ── evaluation_results ───────────────────────────────────────
    op.create_table(
        "evaluation_results",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("run_uuid", uuid_type, sa.ForeignKey("evaluation_runs.run_uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("query_uuid", uuid_type, sa.ForeignKey("evaluation_queries.query_uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("hit_at_1", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("hit_at_3", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("hit_at_5", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("mrr", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("expected_term_hit_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("avg_latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_hits", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("debug_info", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_evaluation_results_run_query", "evaluation_results", ["run_uuid", "query_uuid"], unique=True)
    op.create_index("idx_evaluation_results_run_uuid", "evaluation_results", ["run_uuid"], unique=False)
    op.create_index("idx_evaluation_results_query_uuid", "evaluation_results", ["query_uuid"], unique=False)


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_chunks")
    op.drop_table("evaluation_queries")
    op.drop_table("evaluation_datasets")
