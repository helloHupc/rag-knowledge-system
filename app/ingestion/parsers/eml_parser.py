from __future__ import annotations

import email
import re
from email.header import decode_header
from email.policy import default
from html.parser import HTMLParser
from pathlib import Path

from app.ingestion.types import ParsedBlock


def _decode_rfc2047(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


class _HtmlToTextParser(HTMLParser):
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
        return "\n".join(self._parts).strip()


def _extract_text_from_html(html_content: str) -> str:
    try:
        parser = _HtmlToTextParser()
        parser.feed(html_content)
        result = parser.text()
        return result or html_content
    except Exception:
        return html_content


def _detect_and_decode(payload: bytes, declared_charset: str | None = None) -> str:
    charsets: list[str] = []
    if declared_charset:
        charsets.append(declared_charset)
    charsets.extend(["utf-8", "gbk", "gb2312", "gb18030", "big5", "latin-1"])
    for enc in charsets:
        try:
            return payload.decode(enc, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


class EmlParser:
    """EML email parser implementing the DocumentParser protocol."""

    def parse(self, file_path: Path) -> list[ParsedBlock]:
        raw = file_path.read_bytes()
        msg = email.message_from_bytes(raw, policy=default)

        meta: dict[str, object] = {
            "parser": "eml",
            "message_id": _decode_rfc2047(msg.get("Message-ID", "")),
            "subject": _decode_rfc2047(msg.get("Subject", "")),
            "from": _decode_rfc2047(msg.get("From", "")),
            "to": _decode_rfc2047(msg.get("To", "")),
            "cc": _decode_rfc2047(msg.get("Cc", "")),
            "date": _decode_rfc2047(msg.get("Date", "")),
        }

        blocks: list[ParsedBlock] = []

        # Build header preamble
        header_lines = []
        if meta["subject"]:
            header_lines.append(f"Subject: {meta['subject']}")
        if meta["from"]:
            header_lines.append(f"From: {meta['from']}")
        if meta["to"]:
            header_lines.append(f"To: {meta['to']}")
        if meta["cc"]:
            header_lines.append(f"Cc: {meta['cc']}")
        if meta["date"]:
            header_lines.append(f"Date: {meta['date']}")

        if header_lines:
            blocks.append(
                ParsedBlock(
                    text="\n".join(header_lines),
                    chunk_type="text",
                    section_title=meta.get("subject", None),
                    metadata=dict(meta),
                )
            )

        # Walk all parts
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            is_attachment = "attachment" in disposition.lower()

            if is_attachment:
                attach_name = part.get_filename() or "unnamed_attachment"
                meta_key = f"attachment:{_decode_rfc2047(attach_name)}"
                if meta_key not in meta:
                    meta[meta_key] = "present"
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset()
            text = _detect_and_decode(payload, charset)

            if not text.strip():
                continue

            if content_type == "text/html":
                text = _extract_text_from_html(text)

            section_title = meta.get("subject", None)
            blocks.append(
                ParsedBlock(
                    text=text.strip(),
                    chunk_type="text",
                    section_title=section_title,
                    metadata=dict(meta),
                )
            )

        if not blocks:
            blocks.append(
                ParsedBlock(
                    text=f"Subject: {meta.get('subject', 'No Subject')}",
                    chunk_type="text",
                    metadata=dict(meta),
                )
            )

        return blocks
