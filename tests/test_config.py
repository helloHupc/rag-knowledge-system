from __future__ import annotations

from app.core.config import get_settings


def test_settings_build_database_url():
    settings = get_settings()
    assert settings.sqlalchemy_database_url.startswith("sqlite:///")
    assert settings.resolved_raw_data_dir.name == "raw"
