from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BotPlatform = Literal["feishu", "wecom"]
BotResponseMode = Literal["qa", "search"]


@dataclass(slots=True)
class BotReplyTarget:
    platform: BotPlatform
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None


@dataclass(slots=True)
class BotMessage:
    platform: BotPlatform
    query: str
    target: BotReplyTarget
    event_id: str
    source_module: list[str] | None = None
