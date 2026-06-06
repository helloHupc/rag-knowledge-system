from __future__ import annotations

import base64
import hashlib
import hmac
from collections import OrderedDict
from dataclasses import dataclass
from time import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


_BLOCK_SIZE = 32


def pkcs7_pad(data: bytes, block_size: int = _BLOCK_SIZE) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def pkcs7_unpad(data: bytes, block_size: int = _BLOCK_SIZE) -> bytes:
    if not data:
        raise ValueError("invalid pkcs7 padding")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError("invalid pkcs7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid pkcs7 padding")
    return data[:-pad_len]


def aes_cbc_decrypt_base64(*, ciphertext: str, key: bytes, iv: bytes | None = None) -> bytes:
    payload = base64.b64decode(ciphertext)
    decryptor = Cipher(
        algorithms.AES(key),
        modes.CBC(iv or key[:16]),
        backend=default_backend(),
    ).decryptor()
    return pkcs7_unpad(decryptor.update(payload) + decryptor.finalize())


def aes_cbc_encrypt_base64(*, plaintext: bytes, key: bytes, iv: bytes | None = None) -> str:
    encryptor = Cipher(
        algorithms.AES(key),
        modes.CBC(iv or key[:16]),
        backend=default_backend(),
    ).encryptor()
    payload = encryptor.update(pkcs7_pad(plaintext)) + encryptor.finalize()
    return base64.b64encode(payload).decode("utf-8")


def sha1_sorted_signature(*parts: str) -> str:
    return hashlib.sha1("".join(sorted(parts)).encode("utf-8")).hexdigest()


def feishu_signature(*, timestamp: str, nonce: str, encrypt_key: str, body: bytes) -> str:
    raw = timestamp.encode("utf-8") + nonce.encode("utf-8") + encrypt_key.encode("utf-8") + body
    return hashlib.sha256(raw).hexdigest()


def verify_feishu_signature(
    *, timestamp: str | None, nonce: str | None, signature: str | None, encrypt_key: str, body: bytes
) -> bool:
    if not timestamp or not nonce or not signature or not encrypt_key:
        return False
    expected = feishu_signature(timestamp=timestamp, nonce=nonce, encrypt_key=encrypt_key, body=body)
    return hmac.compare_digest(expected, signature)


def wecom_aes_key(encoding_aes_key: str) -> bytes:
    if len(encoding_aes_key) != 43:
        raise ValueError("WECOM_ENCODING_AES_KEY must be 43 characters")
    return base64.b64decode(encoding_aes_key + "=")


def decrypt_wecom_payload(*, encrypted: str, encoding_aes_key: str) -> tuple[str, str]:
    key = wecom_aes_key(encoding_aes_key)
    payload = aes_cbc_decrypt_base64(ciphertext=encrypted, key=key)
    if len(payload) < 20:
        raise ValueError("invalid wecom encrypted payload")
    msg_len = int.from_bytes(payload[16:20], "big")
    msg = payload[20 : 20 + msg_len].decode("utf-8")
    receive_id = payload[20 + msg_len :].decode("utf-8")
    return msg, receive_id


def encrypt_wecom_payload(*, message_xml: str, receive_id: str, encoding_aes_key: str, random16: bytes | None = None) -> str:
    random_bytes = random16 or b"0" * 16
    if len(random_bytes) != 16:
        raise ValueError("random16 must be 16 bytes")
    msg_bytes = message_xml.encode("utf-8")
    payload = random_bytes + len(msg_bytes).to_bytes(4, "big") + msg_bytes + receive_id.encode("utf-8")
    return aes_cbc_encrypt_base64(plaintext=payload, key=wecom_aes_key(encoding_aes_key))


def decrypt_feishu_payload(*, encrypted: str, encrypt_key: str) -> str:
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    return aes_cbc_decrypt_base64(ciphertext=encrypted, key=key).decode("utf-8")


@dataclass
class DedupCache:
    ttl_seconds: int = 300
    max_size: int = 2048

    def __post_init__(self) -> None:
        self._items: OrderedDict[str, float] = OrderedDict()

    def seen(self, key: str) -> bool:
        now = time()
        expired = [item_key for item_key, expires_at in self._items.items() if expires_at <= now]
        for item_key in expired:
            self._items.pop(item_key, None)
        if key in self._items:
            return True
        self._items[key] = now + self.ttl_seconds
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)
        return False
