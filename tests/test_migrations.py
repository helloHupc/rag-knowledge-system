from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.config import reset_settings_cache
from app.db.runtime import get_engine
from app.db.runtime import reset_db_runtime


def test_schema_tables_exist():
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    assert {
        "documents",
        "document_chunks",
        "ingestion_jobs",
        "users",
        "departments",
        "roles",
        "user_departments",
        "user_roles",
        "retrieval_logs",
        "llm_call_logs",
        "system_configs",
    }.issubset(tables)


def test_alembic_upgrade_head_on_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_sqlite.sqlite3"
    storage_root = tmp_path / "storage"
    reset_settings_cache()
    reset_db_runtime()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("RAW_DATA_DIR", str(storage_root / "raw"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(storage_root / "processed"))
    monkeypatch.setenv("SAMPLE_DATA_DIR", str(storage_root / "samples"))

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "system_configs" in tables
    assert {"users", "departments", "roles", "user_departments", "user_roles"}.issubset(tables)
    reset_settings_cache()
    reset_db_runtime()
