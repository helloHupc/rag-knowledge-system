from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.integrations.bot_crypto import encrypt_wecom_payload, sha1_sorted_signature
from app.integrations.wecom_client import WecomClient

ENCODING_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
TOKEN = "wecom-token"


def _set_wecom_env(monkeypatch):
    monkeypatch.setenv("WECOM_CALLBACK_TOKEN", TOKEN)
    monkeypatch.setenv("WECOM_ENCODING_AES_KEY", ENCODING_KEY)
    monkeypatch.setenv("WECOM_CORP_ID", "corp-id")
    monkeypatch.setenv("WECOM_AGENT_ID", "100001")
    monkeypatch.setenv("WECOM_SECRET", "secret")
    from app.core.config import reset_settings_cache

    reset_settings_cache()


def _signature(encrypted: str, timestamp: str = "1", nonce: str = "nonce") -> str:
    return sha1_sorted_signature(TOKEN, timestamp, nonce, encrypted)


def _message_xml(msg_id: str = "msg-1") -> str:
    return (
        "<xml>"
        "<ToUserName><![CDATA[corp-id]]></ToUserName>"
        "<FromUserName><![CDATA[user-1]]></FromUserName>"
        "<CreateTime>1</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[调岗审批流程是什么？]]></Content>"
        f"<MsgId>{msg_id}</MsgId>"
        "<AgentID>100001</AgentID>"
        "</xml>"
    )


def test_wecom_url_verification_returns_plain_echostr(client, monkeypatch):
    _set_wecom_env(monkeypatch)
    encrypted = encrypt_wecom_payload(
        message_xml="hello-echostr",
        receive_id="corp-id",
        encoding_aes_key=ENCODING_KEY,
        random16=b"1234567890abcdef",
    )

    response = client.get(
        "/api/v1/wecom/callback",
        params={
            "msg_signature": _signature(encrypted),
            "timestamp": "1",
            "nonce": "nonce",
            "echostr": encrypted,
        },
    )

    assert response.status_code == 200
    assert response.text == "hello-echostr"


def test_wecom_url_verification_rejects_bad_signature(client, monkeypatch):
    _set_wecom_env(monkeypatch)
    encrypted = encrypt_wecom_payload(
        message_xml="hello-echostr",
        receive_id="corp-id",
        encoding_aes_key=ENCODING_KEY,
        random16=b"1234567890abcdef",
    )

    response = client.get(
        "/api/v1/wecom/callback",
        params={"msg_signature": "bad", "timestamp": "1", "nonce": "nonce", "echostr": encrypted},
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40102


def test_wecom_callback_submits_background_reply(client, monkeypatch):
    _set_wecom_env(monkeypatch)
    from app.services import background_jobs

    submitted = []
    monkeypatch.setattr(background_jobs.BackgroundJobRunner, "submit", lambda *args, **kwargs: submitted.append(args))
    encrypted = encrypt_wecom_payload(
        message_xml=_message_xml(),
        receive_id="corp-id",
        encoding_aes_key=ENCODING_KEY,
        random16=b"1234567890abcdef",
    )
    body = f"<xml><ToUserName><![CDATA[corp-id]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>"

    response = client.post(
        "/api/v1/wecom/callback",
        params={"msg_signature": _signature(encrypted), "timestamp": "1", "nonce": "nonce"},
        content=body,
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert len(submitted) == 1
    _, platform, query, target, _settings = submitted[0]
    assert platform == "wecom"
    assert query == "调岗审批流程是什么？"
    assert target.user_id == "user-1"


def test_wecom_client_rejects_send_api_errcode(monkeypatch):
    _set_wecom_env(monkeypatch)
    from app.core.config import get_settings

    settings = get_settings()
    WecomClient._token = "token"
    WecomClient._token_expires_at = 9999999999

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errcode": 60020, "errmsg": "not allow to access from your ip"}

    monkeypatch.setattr("app.integrations.wecom_client.httpx.post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(AppError, match="wecom message/send failed"):
        WecomClient(settings).send(type("Target", (), {"user_id": "user-1"})(), "hello")


def test_wecom_callback_deduplicates_msg_id(client, monkeypatch):
    _set_wecom_env(monkeypatch)
    from app.services import background_jobs

    submitted = []
    monkeypatch.setattr(background_jobs.BackgroundJobRunner, "submit", lambda *args, **kwargs: submitted.append(args))
    encrypted = encrypt_wecom_payload(
        message_xml=_message_xml("msg-dedup"),
        receive_id="corp-id",
        encoding_aes_key=ENCODING_KEY,
        random16=b"1234567890abcdef",
    )
    body = f"<xml><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>"
    params = {"msg_signature": _signature(encrypted), "timestamp": "1", "nonce": "nonce"}

    client.post("/api/v1/wecom/callback", params=params, content=body, headers={"Content-Type": "application/xml"})
    client.post("/api/v1/wecom/callback", params=params, content=body, headers={"Content-Type": "application/xml"})

    assert len(submitted) == 1
