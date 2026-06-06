from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_build_database_url():
    settings = get_settings()
    assert settings.sqlalchemy_database_url.startswith("sqlite:///")
    assert settings.resolved_raw_data_dir.name == "raw"


def test_bot_response_mode_validation(monkeypatch):
    monkeypatch.setenv("BOT_RESPONSE_MODE", "invalid")

    with pytest.raises(ValidationError):
        Settings()


def test_feishu_enabled_requires_required_config(monkeypatch):
    monkeypatch.setenv("FEISHU_ENABLED", "true")
    monkeypatch.setenv("FEISHU_APP_ID", "")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "token")

    with pytest.raises(ValidationError):
        Settings()


def test_wecom_enabled_requires_required_config(monkeypatch):
    monkeypatch.setenv("WECOM_ENABLED", "true")
    monkeypatch.setenv("WECOM_CORP_ID", "corp")
    monkeypatch.setenv("WECOM_AGENT_ID", "100001")
    monkeypatch.setenv("WECOM_SECRET", "secret")
    monkeypatch.setenv("WECOM_CALLBACK_TOKEN", "token")
    monkeypatch.setenv("WECOM_ENCODING_AES_KEY", "")

    with pytest.raises(ValidationError):
        Settings()
