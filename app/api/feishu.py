from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_settings_dep
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.bot_crypto import DedupCache
from app.integrations.feishu_client import FeishuClient
from app.schemas.bot import BotReplyTarget
from app.services.background_jobs import BackgroundJobRunner
from app.services.bot_dispatch import run_bot_reply

router = APIRouter(prefix="/feishu", tags=["im-bot"])
_dedup_cache: DedupCache | None = None


def _cache(settings: Settings) -> DedupCache:
    global _dedup_cache
    if _dedup_cache is None or _dedup_cache.ttl_seconds != settings.bot_dedup_ttl_seconds:
        _dedup_cache = DedupCache(ttl_seconds=settings.bot_dedup_ttl_seconds)
    return _dedup_cache


@router.post("/events")
async def feishu_events(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    x_lark_request_timestamp: str | None = Header(default=None),
    x_lark_request_nonce: str | None = Header(default=None),
    x_lark_signature: str | None = Header(default=None),
):
    body = await request.body()
    client = FeishuClient(settings)
    payload = json.loads(body.decode("utf-8") or "{}")
    if "encrypt" in payload:
        payload = client.decrypt_event(payload["encrypt"])

    if payload.get("type") == "url_verification":
        if settings.feishu_verification_token and payload.get("token") != settings.feishu_verification_token:
            raise AppError(code=ErrorCode.BOT_SIGNATURE_INVALID, message="invalid feishu verification token", status_code=401)
        return JSONResponse(content={"challenge": payload.get("challenge", "")})

    if not client.verify_signature(
        timestamp=x_lark_request_timestamp,
        nonce=x_lark_request_nonce,
        signature=x_lark_signature,
        body=body,
    ):
        raise AppError(code=ErrorCode.BOT_SIGNATURE_INVALID, message="invalid feishu signature", status_code=401)

    header = payload.get("header") or {}
    if settings.feishu_verification_token and header.get("token") != settings.feishu_verification_token:
        raise AppError(code=ErrorCode.BOT_SIGNATURE_INVALID, message="invalid feishu verification token", status_code=401)
    if header.get("event_type") != "im.message.receive_v1":
        return JSONResponse(content={"code": 0})

    event_id = str(header.get("event_id") or "")
    if event_id and _cache(settings).seen(f"feishu:{event_id}"):
        return JSONResponse(content={"code": 0})

    event = payload.get("event") or {}
    message = event.get("message") or {}
    if message.get("message_type") != "text":
        return JSONResponse(content={"code": 0})
    if message.get("chat_type") == "group" and not message.get("mentions"):
        return JSONResponse(content={"code": 0})

    content = json.loads(message.get("content") or "{}")
    query = str(content.get("text") or "").strip()
    for mention in message.get("mentions") or []:
        key = mention.get("key")
        if key:
            query = query.replace(key, "")
    query = query.strip()
    if not query:
        return JSONResponse(content={"code": 0})

    target = BotReplyTarget(
        platform="feishu",
        chat_id=message.get("chat_id"),
        message_id=message.get("message_id"),
    )
    BackgroundJobRunner.submit(run_bot_reply, "feishu", query, target, settings)
    return JSONResponse(content={"code": 0})
