from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SourceDocument:
    file_name: str
    content: bytes
    mime_type: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class SourceReadResult:
    documents: list[SourceDocument]
    source_name: str
    metadata: dict = field(default_factory=dict)
