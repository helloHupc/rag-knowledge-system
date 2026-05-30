from __future__ import annotations

from pathlib import Path

from app.ingestion.parsers.common import normalize_text
from app.ingestion.types import ParsedBlock


class MarkdownParser:
    def parse(self, file_path: Path) -> list[ParsedBlock]:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        blocks: list[ParsedBlock] = []
        current_heading: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            nonlocal buffer
            text = normalize_text("\n".join(buffer))
            if text:
                blocks.append(
                    ParsedBlock(
                        text=text,
                        section_title=current_heading,
                        metadata={"parser": "markdown"},
                    )
                )
            buffer = []

        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
                if heading:
                    flush()
                    current_heading = heading
                    continue
            buffer.append(line)

        flush()
        return blocks
