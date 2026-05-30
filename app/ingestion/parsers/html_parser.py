from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from app.ingestion.parsers.common import normalize_text
from app.ingestion.types import ParsedBlock


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag in {"p", "br", "div", "section", "article", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in {"p", "div", "section", "article", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return normalize_text(" ".join(self._parts))


class HtmlParser:
    def parse(self, file_path: Path) -> list[ParsedBlock]:
        parser = _ReadableHtmlParser()
        parser.feed(file_path.read_text(encoding="utf-8", errors="ignore"))
        text = parser.text()
        if not text:
            return []
        return [
            ParsedBlock(
                text=text,
                metadata={"parser": "html"},
            )
        ]
