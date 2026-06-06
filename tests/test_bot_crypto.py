from __future__ import annotations

from app.integrations.bot_crypto import (
    DedupCache,
    decrypt_wecom_payload,
    encrypt_wecom_payload,
    sha1_sorted_signature,
)


def test_wecom_encrypt_decrypt_roundtrip():
    encoding_key = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
    xml = "<xml><Content>hello</Content></xml>"

    encrypted = encrypt_wecom_payload(
        message_xml=xml,
        receive_id="corp-id",
        encoding_aes_key=encoding_key,
        random16=b"1234567890abcdef",
    )

    plaintext, receive_id = decrypt_wecom_payload(encrypted=encrypted, encoding_aes_key=encoding_key)
    assert plaintext == xml
    assert receive_id == "corp-id"


def test_sha1_sorted_signature_is_order_independent():
    assert sha1_sorted_signature("token", "1", "nonce", "payload") == sha1_sorted_signature(
        "payload", "nonce", "token", "1"
    )


def test_dedup_cache_reports_repeated_key():
    cache = DedupCache(ttl_seconds=300)
    assert cache.seen("message-1") is False
    assert cache.seen("message-1") is True
