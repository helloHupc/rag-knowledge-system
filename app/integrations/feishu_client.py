from __future__ import annotations

import json
from time import time

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.bot_crypto import decrypt_feishu_payload, verify_feishu_signature
from app.schemas.bot import BotReplyTarget


class FeishuClient:
    _token: str | None = None
    _token_expires_at: float = 0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify_signature(self, *, timestamp: str | None, nonce: str | None, signature: str | None, body: bytes) -> bool:
        if not self.settings.feishu_encrypt_key:
            return True
        return verify_feishu_signature(
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
            encrypt_key=self.settings.feishu_encrypt_key,
            body=body,
        )

    def decrypt_event(self, encrypted: str) -> dict:
        if not self.settings.feishu_encrypt_key:
            raise AppError(code=ErrorCode.BOT_CONFIG_MISSING, message="FEISHU_ENCRYPT_KEY is required", status_code=400)
        return json.loads(decrypt_feishu_payload(encrypted=encrypted, encrypt_key=self.settings.feishu_encrypt_key))

    def tenant_access_token(self) -> str:
        now = time()
        if self.__class__._token and self.__class__._token_expires_at - 300 > now:
            return self.__class__._token
        response = httpx.post(
            f"{self.settings.feishu_base_url.rstrip('/')}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.settings.feishu_app_id, "app_secret": self.settings.feishu_app_secret},
            timeout=self.settings.provider_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("tenant_access_token")
        if not token:
            raise AppError(code=ErrorCode.BOT_CONFIG_MISSING, message=f"failed to get feishu token: {payload}", status_code=502)
        self.__class__._token = token
        self.__class__._token_expires_at = now + int(payload.get("expire", 7200))
        return token

    def reply(self, target: BotReplyTarget, text: str) -> dict:
        token = self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        content = json.dumps({"text": text}, ensure_ascii=False)
        if target.message_id:
            url = f"{self.settings.feishu_base_url.rstrip('/')}/open-apis/im/v1/messages/{target.message_id}/reply"
            payload = {"msg_type": "text", "content": content}
        else:
            url = f"{self.settings.feishu_base_url.rstrip('/')}/open-apis/im/v1/messages?receive_id_type=chat_id"
            payload = {"receive_id": target.chat_id, "msg_type": "text", "content": content}
        response = httpx.post(url, headers=headers, json=payload, timeout=self.settings.provider_timeout_seconds)
        response.raise_for_status()
        return response.json()
