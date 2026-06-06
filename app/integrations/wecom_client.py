from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.bot_crypto import decrypt_wecom_payload, sha1_sorted_signature
from app.schemas.bot import BotReplyTarget


def _ensure_wecom_success(payload: dict, *, action: str) -> None:
    errcode = payload.get("errcode", 0)
    if errcode not in (0, "0", None):
        raise AppError(code=ErrorCode.BOT_CONFIG_MISSING, message=f"wecom {action} failed: {payload}", status_code=502)


class WecomClient:
    _token: str | None = None
    _token_expires_at: float = 0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify_signature(self, *, signature: str | None, timestamp: str | None, nonce: str | None, encrypted: str | None) -> bool:
        if not all([signature, timestamp, nonce, encrypted, self.settings.wecom_callback_token]):
            return False
        expected = sha1_sorted_signature(self.settings.wecom_callback_token, timestamp or "", nonce or "", encrypted or "")
        return expected == signature

    def decrypt_payload(self, encrypted: str) -> tuple[str, str]:
        if not self.settings.wecom_encoding_aes_key:
            raise AppError(code=ErrorCode.BOT_CONFIG_MISSING, message="WECOM_ENCODING_AES_KEY is required", status_code=400)
        return decrypt_wecom_payload(encrypted=encrypted, encoding_aes_key=self.settings.wecom_encoding_aes_key)

    def access_token(self) -> str:
        from time import time
        now = time()
        if self.__class__._token and self.__class__._token_expires_at - 300 > now:
            return self.__class__._token
        response = httpx.get(
            f"{self.settings.wecom_base_url.rstrip('/')}/cgi-bin/gettoken",
            params={"corpid": self.settings.wecom_corp_id, "corpsecret": self.settings.wecom_secret},
            timeout=self.settings.provider_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        _ensure_wecom_success(payload, action="gettoken")
        token = payload.get("access_token")
        if not token:
            raise AppError(code=ErrorCode.BOT_CONFIG_MISSING, message=f"failed to get wecom token: {payload}", status_code=502)
        self.__class__._token = token
        self.__class__._token_expires_at = now + int(payload.get("expires_in", 7200))
        return token

    def send(self, target: BotReplyTarget, text: str) -> dict:
        token = self.access_token()
        response = httpx.post(
            f"{self.settings.wecom_base_url.rstrip('/')}/cgi-bin/message/send",
            params={"access_token": token},
            json={
                "touser": target.user_id,
                "msgtype": "text",
                "agentid": int(self.settings.wecom_agent_id or 0),
                "text": {"content": text},
            },
            timeout=self.settings.provider_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        _ensure_wecom_success(payload, action="message/send")
        return payload
