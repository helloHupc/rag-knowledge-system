from __future__ import annotations

import json

from app.integrations.bot_crypto import feishu_signature


def _event_payload(event_id: str = "evt-1") -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "token": "verify-token",
        },
        "event": {
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "调岗审批流程是什么？"}, ensure_ascii=False),
            }
        },
    }


def test_feishu_url_verification_returns_platform_contract(client, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    response = client.post(
        "/api/v1/feishu/events",
        json={"type": "url_verification", "token": "verify-token", "challenge": "abc"},
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "abc"}


def test_feishu_rejects_invalid_verification_token(client, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    response = client.post(
        "/api/v1/feishu/events",
        json={"type": "url_verification", "token": "wrong", "challenge": "abc"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40102


def test_feishu_event_submits_background_reply(client, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    from app.core.config import reset_settings_cache
    from app.services import background_jobs

    reset_settings_cache()
    submitted = []

    def fake_submit(fn, *args, **kwargs):
        submitted.append((fn, args, kwargs))

    monkeypatch.setattr(background_jobs.BackgroundJobRunner, "submit", fake_submit)
    response = client.post("/api/v1/feishu/events", json=_event_payload())

    assert response.status_code == 200
    assert response.json() == {"code": 0}
    assert len(submitted) == 1
    _, args, _ = submitted[0]
    assert args[0] == "feishu"
    assert args[1] == "调岗审批流程是什么？"
    assert args[2].message_id == "om_1"


def test_feishu_event_deduplicates_event_id(client, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    from app.core.config import reset_settings_cache
    from app.services import background_jobs

    reset_settings_cache()
    submitted = []
    monkeypatch.setattr(background_jobs.BackgroundJobRunner, "submit", lambda *args, **kwargs: submitted.append(args))

    client.post("/api/v1/feishu/events", json=_event_payload("evt-dedup"))
    client.post("/api/v1/feishu/events", json=_event_payload("evt-dedup"))

    assert len(submitted) == 1


def test_feishu_signature_checked_when_encrypt_key_configured(client, monkeypatch):
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "verify-token")
    monkeypatch.setenv("FEISHU_ENCRYPT_KEY", "encrypt-key")
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    body = json.dumps(_event_payload()).encode("utf-8")
    response = client.post(
        "/api/v1/feishu/events",
        content=body,
        headers={
            "X-Lark-Request-Timestamp": "1",
            "X-Lark-Request-Nonce": "nonce",
            "X-Lark-Signature": feishu_signature(
                timestamp="1", nonce="nonce", encrypt_key="encrypt-key", body=body
            ),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200

    bad = client.post(
        "/api/v1/feishu/events",
        content=body,
        headers={
            "X-Lark-Request-Timestamp": "1",
            "X-Lark-Request-Nonce": "nonce",
            "X-Lark-Signature": "bad",
            "Content-Type": "application/json",
        },
    )
    assert bad.status_code == 401
