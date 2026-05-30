from __future__ import annotations

from typing import Protocol

from app.sources.types import SourceReadResult


class SourceConnector(Protocol):
    name: str

    async def read(self) -> SourceReadResult:
        ...
