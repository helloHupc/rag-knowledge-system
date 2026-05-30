from __future__ import annotations

from pathlib import Path

from app.ingestion.parsers.common import normalize_text
from app.ingestion.types import ParsedBlock


class TextParser:
    def parse(self, file_path: Path) -> list[ParsedBlock]:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        text = normalize_text(raw_text)
        if not text:
            return []
        return [
            ParsedBlock(
                text=text,
                metadata={"parser": "text"},
            )
        ]
