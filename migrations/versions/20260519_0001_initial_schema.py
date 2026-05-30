"""initial schema

Revision ID: 20260519_0001
Revises:
Create Date: 2026-05-19 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260519_0001"
down_revision = None
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


def _maybe_create_postgres_support(dialect_name: str) -> None:
    if dialect_name == "postgresql":
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    json_type = _json_type(dialect_name)
    uuid_type = _uuid_type(dialect_name)
    pk_type = _pk_type(dialect_name)

    _maybe_create_postgres_support(dialect_name)

    server_uuid = sa.text("gen_random_uuid()") if dialect_name == "postgresql" else None
    server_now = sa.text("CURRENT_TIMESTAMP")
    json_empty_array = sa.text("'[]'::jsonb") if dialect_name == "postgresql" else sa.text("'[]'")
    json_empty_object = sa.text("'{}'::jsonb") if dialect_name == "postgresql" else sa.text("'{}'")

    op.create_table(
        "documents",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("doc_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_ext", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=128)),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column("version", sa.String(length=64), nullable=False, server_default="v1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("index_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("access_level", sa.String(length=64), nullable=False, server_default="internal"),
        sa.Column("owner_dept", sa.String(length=64)),
        sa.Column("owner_role", sa.String(length=64)),
        sa.Column("tags", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("extra_meta", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("updated_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("uq_documents_doc_uuid", "documents", ["doc_uuid"], unique=True)
    op.create_index("idx_documents_source_module", "documents", ["source_module"], unique=False)
    op.create_index("idx_documents_source_type", "documents", ["source_type"], unique=False)
    op.create_index("idx_documents_status", "documents", ["status"], unique=False)
    op.create_index("idx_documents_parse_status", "documents", ["parse_status"], unique=False)
    op.create_index("idx_documents_index_status", "documents", ["index_status"], unique=False)
    op.create_index("idx_documents_access_level", "documents", ["access_level"], unique=False)
    op.create_index("idx_documents_owner_dept", "documents", ["owner_dept"], unique=False)
    op.create_index("idx_documents_created_at", "documents", ["created_at"], unique=False)
    op.create_index("idx_documents_file_hash", "documents", ["file_hash"], unique=False)
    if dialect_name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_documents_hash_version "
            "ON documents(file_hash, version) WHERE deleted_at IS NULL;"
        )

    op.create_table(
        "document_chunks",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("chunk_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("doc_uuid", uuid_type, sa.ForeignKey("documents.doc_uuid", ondelete="CASCADE"), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("uq_document_chunks_chunk_uuid", "document_chunks", ["chunk_uuid"], unique=True)
    op.create_index("idx_document_chunks_doc_uuid", "document_chunks", ["doc_uuid"], unique=False)
    op.create_index("idx_document_chunks_page_no", "document_chunks", ["page_no"], unique=False)
    op.create_index("idx_document_chunks_sheet_name", "document_chunks", ["sheet_name"], unique=False)
    op.create_index("idx_document_chunks_chunk_type", "document_chunks", ["chunk_type"], unique=False)
    op.create_index("idx_document_chunks_vector_id", "document_chunks", ["vector_id"], unique=False)
    if dialect_name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_document_chunks_doc_chunk_index "
            "ON document_chunks(doc_uuid, chunk_index) WHERE deleted_at IS NULL;"
        )
        op.execute("CREATE INDEX idx_document_chunks_metadata_json ON document_chunks USING GIN(metadata_json);")

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("job_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("doc_uuid", uuid_type, sa.ForeignKey("documents.doc_uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False, server_default="ingest"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("current_step", sa.String(length=64), nullable=False, server_default="created"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_ingestion_jobs_job_uuid", "ingestion_jobs", ["job_uuid"], unique=True)
    op.create_index("idx_ingestion_jobs_doc_uuid", "ingestion_jobs", ["doc_uuid"], unique=False)
    op.create_index("idx_ingestion_jobs_status", "ingestion_jobs", ["status"], unique=False)
    op.create_index("idx_ingestion_jobs_current_step", "ingestion_jobs", ["current_step"], unique=False)
    op.create_index("idx_ingestion_jobs_created_at", "ingestion_jobs", ["created_at"], unique=False)

    op.create_table(
        "access_policies",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("policy_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("effect_scope", sa.String(length=32), nullable=False, server_default="allow"),
        sa.Column("role_codes", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("dept_codes", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("user_ids", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("extra_rules", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_access_policies_policy_uuid", "access_policies", ["policy_uuid"], unique=True)
    op.create_index("idx_access_policies_resource", "access_policies", ["resource_type", "resource_id"], unique=False)
    if dialect_name == "postgresql":
        op.execute("CREATE INDEX idx_access_policies_role_codes ON access_policies USING GIN(role_codes);")
        op.execute("CREATE INDEX idx_access_policies_dept_codes ON access_policies USING GIN(dept_codes);")
        op.execute("CREATE INDEX idx_access_policies_user_ids ON access_policies USING GIN(user_ids);")

    op.create_table(
        "retrieval_logs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("log_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("trace_id", sa.String(length=128)),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text()),
        sa.Column("query_intent", sa.String(length=64)),
        sa.Column("filters_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("user_context_json", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_latency_ms", sa.Integer()),
        sa.Column("generation_latency_ms", sa.Integer()),
        sa.Column("total_latency_ms", sa.Integer()),
        sa.Column("matched_documents_json", json_type, nullable=False, server_default=json_empty_array),
        sa.Column("response_excerpt", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_retrieval_logs_log_uuid", "retrieval_logs", ["log_uuid"], unique=True)
    op.create_index("idx_retrieval_logs_trace_id", "retrieval_logs", ["trace_id"], unique=False)
    op.create_index("idx_retrieval_logs_query_intent", "retrieval_logs", ["query_intent"], unique=False)
    op.create_index("idx_retrieval_logs_created_at", "retrieval_logs", ["created_at"], unique=False)
    if dialect_name == "postgresql":
        op.execute("CREATE INDEX idx_retrieval_logs_filters_json ON retrieval_logs USING GIN(filters_json);")
        op.execute("CREATE INDEX idx_retrieval_logs_user_context_json ON retrieval_logs USING GIN(user_context_json);")

    op.create_table(
        "llm_call_logs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("log_uuid", uuid_type, nullable=False, server_default=server_uuid),
        sa.Column("trace_id", sa.String(length=128)),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("request_tokens", sa.Integer()),
        sa.Column("response_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_llm_call_logs_log_uuid", "llm_call_logs", ["log_uuid"], unique=True)
    op.create_index("idx_llm_call_logs_trace_id", "llm_call_logs", ["trace_id"], unique=False)
    op.create_index("idx_llm_call_logs_provider_type", "llm_call_logs", ["provider_type"], unique=False)
    op.create_index("idx_llm_call_logs_model_name", "llm_call_logs", ["model_name"], unique=False)
    op.create_index("idx_llm_call_logs_created_at", "llm_call_logs", ["created_at"], unique=False)

    op.create_table(
        "system_configs",
        sa.Column("id", pk_type, primary_key=True, autoincrement=True),
        sa.Column("config_key", sa.String(length=128), nullable=False),
        sa.Column("config_value", json_type, nullable=False, server_default=json_empty_object),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=server_now),
    )
    op.create_index("uq_system_configs_config_key", "system_configs", ["config_key"], unique=True)

    system_configs = sa.table(
        "system_configs",
        sa.column("id", pk_type),
        sa.column("config_key", sa.String()),
        sa.column("config_value", json_type),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        system_configs,
        [
            {
                "id": 1,
                "config_key": "chunking.default",
                "config_value": {
                    "max_chars": 1200,
                    "overlap_chars": 150,
                    "pdf_strategy": "heading_first",
                    "docx_strategy": "heading_first",
                    "xlsx_strategy": "sheet_table_row_group",
                },
                "description": "默认切片配置",
            },
            {
                "id": 2,
                "config_key": "retrieval.default",
                "config_value": {
                    "top_k": 8,
                    "min_score": 0.2,
                    "use_rerank": False,
                },
                "description": "默认检索配置",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_system_configs_config_key", table_name="system_configs")
    op.drop_table("system_configs")
    op.drop_index("idx_llm_call_logs_created_at", table_name="llm_call_logs")
    op.drop_index("idx_llm_call_logs_model_name", table_name="llm_call_logs")
    op.drop_index("idx_llm_call_logs_provider_type", table_name="llm_call_logs")
    op.drop_index("idx_llm_call_logs_trace_id", table_name="llm_call_logs")
    op.drop_index("uq_llm_call_logs_log_uuid", table_name="llm_call_logs")
    op.drop_table("llm_call_logs")
    op.drop_index("idx_retrieval_logs_created_at", table_name="retrieval_logs")
    op.drop_index("idx_retrieval_logs_query_intent", table_name="retrieval_logs")
    op.drop_index("idx_retrieval_logs_trace_id", table_name="retrieval_logs")
    op.drop_index("uq_retrieval_logs_log_uuid", table_name="retrieval_logs")
    op.drop_table("retrieval_logs")
    op.drop_index("idx_access_policies_resource", table_name="access_policies")
    op.drop_index("uq_access_policies_policy_uuid", table_name="access_policies")
    op.drop_table("access_policies")
    op.drop_index("idx_ingestion_jobs_created_at", table_name="ingestion_jobs")
    op.drop_index("idx_ingestion_jobs_current_step", table_name="ingestion_jobs")
    op.drop_index("idx_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("idx_ingestion_jobs_doc_uuid", table_name="ingestion_jobs")
    op.drop_index("uq_ingestion_jobs_job_uuid", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("idx_document_chunks_vector_id", table_name="document_chunks")
    op.drop_index("idx_document_chunks_chunk_type", table_name="document_chunks")
    op.drop_index("idx_document_chunks_sheet_name", table_name="document_chunks")
    op.drop_index("idx_document_chunks_page_no", table_name="document_chunks")
    op.drop_index("idx_document_chunks_doc_uuid", table_name="document_chunks")
    op.drop_index("uq_document_chunks_chunk_uuid", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("idx_documents_file_hash", table_name="documents")
    op.drop_index("idx_documents_created_at", table_name="documents")
    op.drop_index("idx_documents_owner_dept", table_name="documents")
    op.drop_index("idx_documents_access_level", table_name="documents")
    op.drop_index("idx_documents_index_status", table_name="documents")
    op.drop_index("idx_documents_parse_status", table_name="documents")
    op.drop_index("idx_documents_status", table_name="documents")
    op.drop_index("idx_documents_source_type", table_name="documents")
    op.drop_index("idx_documents_source_module", table_name="documents")
    op.drop_index("uq_documents_doc_uuid", table_name="documents")
    op.drop_table("documents")
