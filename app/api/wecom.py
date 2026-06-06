from __future__ import annotations

import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import get_settings_dep
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.bot_crypto import DedupCache
from app.integrations.wecom_client import WecomClient
from app.schemas.bot import BotReplyTarget
from app.services.background_jobs import BackgroundJobRunner
from app.services.bot_dispatch import run_bot_reply

router = APIRouter(prefix="/wecom", tags=["im-bot"])
_dedup_cache: DedupCache | None = None


def _cache(settings: Settings) -> DedupCache:
    global _dedup_cache
    if _dedup_cache is None or _dedup_cache.ttl_seconds != settings.bot_dedup_ttl_seconds:
        _dedup_cache = DedupCache(ttl_seconds=settings.bot_dedup_ttl_seconds)
    return _dedup_cache


def _xml_text(root: ET.Element, name: str) -> str | None:
    node = root.find(name)
    return node.text if node is not None else None


@router.get("/callback", response_class=PlainTextResponse)
def wecom_verify_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    settings: Settings = Depends(get_settings_dep),
):
    client = WecomClient(settings)
    if not client.verify_signature(signature=msg_signature, timestamp=timestamp, nonce=nonce, encrypted=echostr):
        raise AppError(code=ErrorCode.BOT_SIGNATURE_INVALID, message="invalid wecom signature", status_code=401)
    plaintext, _receive_id = client.decrypt_payload(echostr)
    return PlainTextResponse(plaintext)


@router.post("/callback", response_class=PlainTextResponse)
async def wecom_callback(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    settings: Settings = Depends(get_settings_dep),
):
    body = await request.body()
    root = ET.fromstring(body.decode("utf-8"))
    encrypted = _xml_text(root, "Encrypt")
    if not encrypted:
        raise AppError(code=ErrorCode.INVALID_REQUEST, message="missing wecom Encrypt", status_code=400)

    client = WecomClient(settings)
    if not client.verify_signature(signature=msg_signature, timestamp=timestamp, nonce=nonce, encrypted=encrypted):
        raise AppError(code=ErrorCode.BOT_SIGNATURE_INVALID, message="invalid wecom signature", status_code=401)

    plaintext_xml, _receive_id = client.decrypt_payload(encrypted)
    msg_root = ET.fromstring(plaintext_xml)
    msg_type = _xml_text(msg_root, "MsgType")
    if msg_type != "text":
        return PlainTextResponse("")

    msg_id = _xml_text(msg_root, "MsgId") or ""
    if msg_id and _cache(settings).seen(f"wecom:{msg_id}"):
        return PlainTextResponse("")

    query = (_xml_text(msg_root, "Content") or "").strip()
    user_id = (_xml_text(msg_root, "FromUserName") or "").strip()
    if not query or not user_id:
        return PlainTextResponse("")

    target = BotReplyTarget(platform="wecom", user_id=user_id)
    BackgroundJobRunner.submit(run_bot_reply, "wecom", query, target, settings)
    return PlainTextResponse("")
