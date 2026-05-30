from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from app.ingestion.types import ParsedBlock

MAX_MESSAGES_PER_BLOCK = 80


class ChatParser:
    """Chat log parser supporting JSONL and CSV formats."""

    def parse(self, file_path: Path) -> list[ParsedBlock]:
        suffix = file_path.suffix.lower()
        if suffix in (".jsonl",):
            return self._parse_jsonl(file_path)
        if suffix in (".csv",):
            return self._parse_csv(file_path)
        return self._parse_jsonl(file_path)

    def _parse_jsonl(self, file_path: Path) -> list[ParsedBlock]:
        thread_map: dict[str, list[dict]] = {}
        thread_order: list[str] = []

        with file_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                speaker = record.get("speaker") or record.get("name") or record.get("user") or "unknown"
                timestamp = record.get("timestamp") or record.get("time") or record.get("created_at") or ""
                content = record.get("content") or record.get("message") or record.get("text") or ""
                channel = record.get("channel") or record.get("room") or ""
                thread_id = record.get("thread_id") or record.get("conversation_id") or channel or "default"

                if thread_id not in thread_map:
                    thread_map[thread_id] = []
                    thread_order.append(thread_id)
                thread_map[thread_id].append({
                    "speaker": str(speaker),
                    "timestamp": str(timestamp),
                    "content": str(content),
                    "channel": str(channel),
                    "thread_id": str(thread_id),
                })

        return self._build_blocks(thread_map, thread_order)

    def _parse_csv(self, file_path: Path) -> list[ParsedBlock]:
        thread_map: dict[str, list[dict]] = {}
        thread_order: list[str] = []

        with file_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return []

            field_map = self._detect_csv_fields(reader.fieldnames)
            for row in reader:
                speaker = row.get(field_map["speaker"], "unknown")
                timestamp = row.get(field_map["timestamp"], "")
                content = row.get(field_map["content"], "")
                channel = row.get(field_map["channel"], "")
                thread_id = row.get(field_map["thread_id"], channel or "default")

                if thread_id not in thread_map:
                    thread_map[thread_id] = []
                    thread_order.append(thread_id)
                thread_map[thread_id].append({
                    "speaker": str(speaker),
                    "timestamp": str(timestamp),
                    "content": str(content),
                    "channel": str(channel),
                    "thread_id": str(thread_id),
                })

        return self._build_blocks(thread_map, thread_order)

    @staticmethod
    def _detect_csv_fields(fieldnames: list[str]) -> dict[str, str]:
        normalized = [f.strip().lower() for f in fieldnames]
        mapping = {}
        for key in ("speaker", "name", "user", "author"):
            if key in normalized:
                mapping["speaker"] = fieldnames[normalized.index(key)]
                break
        else:
            mapping["speaker"] = fieldnames[0] if fieldnames else "speaker"

        for key in ("timestamp", "time", "created_at", "date"):
            if key in normalized:
                mapping["timestamp"] = fieldnames[normalized.index(key)]
                break
        else:
            mapping["timestamp"] = fieldnames[1] if len(fieldnames) > 1 else "timestamp"

        for key in ("content", "message", "text", "body"):
            if key in normalized:
                mapping["content"] = fieldnames[normalized.index(key)]
                break
        else:
            mapping["content"] = fieldnames[2] if len(fieldnames) > 2 else "content"

        for key in ("channel", "room", "group"):
            if key in normalized:
                mapping["channel"] = fieldnames[normalized.index(key)]
                break
        else:
            mapping["channel"] = "channel"

        for key in ("thread_id", "conversation_id", "thread", "conv_id"):
            if key in normalized:
                mapping["thread_id"] = fieldnames[normalized.index(key)]
                break
        else:
            mapping["thread_id"] = "thread_id"

        return mapping

    def _build_blocks(
        self,
        thread_map: dict[str, list[dict]],
        thread_order: list[str],
    ) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []

        for thread_id in thread_order:
            messages = thread_map[thread_id]
            for i in range(0, len(messages), MAX_MESSAGES_PER_BLOCK):
                batch = messages[i : i + MAX_MESSAGES_PER_BLOCK]
                chunk_text = self._format_batch(batch)

                blocks.append(
                    ParsedBlock(
                        text=chunk_text,
                        chunk_type="text",
                        section_title=f"Chat: {thread_id}",
                        metadata={
                            "parser": "chat",
                            "thread_id": thread_id,
                            "channel": batch[0].get("channel", ""),
                            "message_count": len(batch),
                            "total_in_thread": len(messages),
                        },
                    )
                )

        return blocks

    @staticmethod
    def _format_batch(messages: list[dict]) -> str:
        lines: list[str] = []
        for msg in messages:
            speaker = msg.get("speaker", "unknown")
            ts = msg.get("timestamp", "")
            content = msg.get("content", "")
            if ts:
                lines.append(f"[{ts}] {speaker}: {content}")
            else:
                lines.append(f"{speaker}: {content}")
        return "\n".join(lines)
