from __future__ import annotations

from dataclasses import dataclass
import re
import uuid
from typing import Protocol

from app.integrations.embedding import EmbeddingProvider
from app.ingestion.types import ChunkingOptions, ChunkPayload, ParsedBlock


try:
    from app.core.config import get_settings
except ImportError:
    get_settings = None  # type: ignore[assignment]


DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150
HEADING_MAX_CHARS = 90
REPEATED_BOILERPLATE_MAX_CHARS = 160
REPEATED_BOILERPLATE_EDGE_LINES = 4


@dataclass(slots=True)
class StructuralSection:
    text: str
    heading: str | None = None
    heading_level: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    split_reason: str = "block"


@dataclass(slots=True)
class ParentSegment:
    text: str
    metadata: dict


@dataclass(slots=True)
class ParentSegmentSource:
    block: ParsedBlock
    group_uuid: str
    segment: ParentSegment


@dataclass(slots=True)
class ParentSectionSource:
    block: ParsedBlock
    section_index: int
    section: StructuralSection


@dataclass(slots=True)
class SemanticSegment:
    text: str
    sentence_start: int
    sentence_end: int
    split_reason: str
    breakpoint_score: float | None = None


@dataclass(slots=True)
class ChatMessage:
    speaker: str
    date_str: str
    time_str: str
    content: str
    content_type: str = "text"
    quoted_speaker: str | None = None
    quoted_content: str | None = None
    raw_text: str = ""


@dataclass(slots=True)
class ChatSegment:
    messages: list[ChatMessage]
    segment_index: int
    split_reason: str


class ChunkingStrategy(Protocol):
    name: str
    params_schema: dict

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        ...


def estimate_token_count(text: str) -> int:
    return len(text.split())


def _clean_metadata(metadata: dict) -> dict:
    return {key: value for key, value in metadata.items() if not str(key).startswith("_")}


def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + max_chars, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(end - overlap_chars, start + 1)

    return chunks


class FixedChunkingStrategy:
    name = "fixed"
    params_schema = {
        "type": "object",
        "properties": {
            "max_chars": {"type": "integer", "default": 1200, "minimum": 100, "maximum": 8000},
            "overlap_chars": {"type": "integer", "default": 150, "minimum": 0, "maximum": 2000},
        },
    }

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        chunks: list[ChunkPayload] = []
        chunk_index = 0

        for block in parsed_blocks:
            text_parts = split_text(
                block.text,
                max_chars=options.max_chars,
                overlap_chars=options.overlap_chars,
            )
            for part_index, chunk_text in enumerate(text_parts, start=1):
                metadata = _clean_metadata(block.metadata)
                metadata["chunking_strategy"] = self.name
                metadata["split_part"] = part_index
                metadata["split_total"] = len(text_parts)
                chunks.append(_build_chunk_payload(chunk_index, block, chunk_text, metadata))
                chunk_index += 1

        return chunks


class StructuralChunkingStrategy:
    name = "structural"
    params_schema = {
        "type": "object",
        "properties": {
            "max_chars": {"type": "integer", "default": 1200, "minimum": 100, "maximum": 8000},
            "overlap_chars": {"type": "integer", "default": 150, "minimum": 0, "maximum": 2000},
        },
    }

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        chunks: list[ChunkPayload] = []
        chunk_index = 0
        pending_heading_sections: list[StructuralSection] = []
        pending_heading_block: ParsedBlock | None = None
        buffered_block: ParsedBlock | None = None
        buffered_sections: list[StructuralSection] = []
        parsed_blocks = self._remove_repeated_page_boilerplate(parsed_blocks)

        def emit_sections(block: ParsedBlock, sections: list[StructuralSection]) -> None:
            nonlocal chunk_index
            if not sections:
                return

            metadata = _clean_metadata(block.metadata)
            metadata["chunking_strategy"] = self.name

            for section_index, section in enumerate(sections, start=1):
                text_parts = split_text(
                    section.text,
                    max_chars=options.max_chars,
                    overlap_chars=options.overlap_chars,
                )
                for part_index, chunk_text in enumerate(text_parts, start=1):
                    chunk_metadata = dict(metadata)
                    chunk_metadata["structural_section_index"] = section_index
                    chunk_metadata["structural_section_total"] = len(sections)
                    chunk_metadata["section_part"] = section_index
                    chunk_metadata["section_total"] = len(sections)
                    chunk_metadata["split_part"] = part_index
                    chunk_metadata["split_total"] = len(text_parts)
                    chunk_metadata["split_reason"] = section.split_reason
                    if section.heading or block.section_title:
                        chunk_metadata["section_heading"] = section.heading or block.section_title
                    if section.heading_level is not None:
                        chunk_metadata["section_heading_level"] = section.heading_level
                    if section.start_line is not None:
                        chunk_metadata["section_start_line"] = section.start_line
                    if section.end_line is not None:
                        chunk_metadata["section_end_line"] = section.end_line
                    chunks.append(_build_chunk_payload(chunk_index, block, chunk_text, chunk_metadata))
                    chunk_index += 1

        def flush_buffer() -> None:
            nonlocal buffered_block, buffered_sections
            if buffered_block and buffered_sections:
                emit_sections(buffered_block, buffered_sections)
            buffered_block = None
            buffered_sections = []

        def buffer_sections(block: ParsedBlock, sections: list[StructuralSection]) -> None:
            nonlocal buffered_block, buffered_sections
            if not sections:
                return

            if (
                buffered_block
                and buffered_sections
                and self._can_merge_cross_page_continuation(buffered_block, buffered_sections[-1], block, sections[0], options.max_chars)
            ):
                buffered_sections[-1] = self._merge_structural_sections(buffered_sections[-1], sections.pop(0))
                if not sections:
                    return

            while (
                buffered_block
                and buffered_sections
                and sections
                and self._can_merge_small_related_numbered_sections(buffered_sections[-1], sections[0], options.max_chars)
            ):
                buffered_sections[-1] = self._merge_structural_sections(buffered_sections[-1], sections.pop(0))
                if not sections:
                    return

            flush_buffer()
            buffered_block = block
            buffered_sections = sections

        for block in parsed_blocks:
            sections = self._split_structural_block(block.text)
            sections = self._merge_small_continuation_sections(sections, max_chars=options.max_chars)
            sections = self._merge_small_related_numbered_sections(sections, max_chars=options.max_chars)

            if pending_heading_sections and pending_heading_block and not self._can_attach_pending_heading(
                pending_heading_block,
                block,
            ):
                buffer_sections(pending_heading_block, pending_heading_sections)
                pending_heading_sections = []
                pending_heading_block = None

            if pending_heading_sections:
                attached = self._prepend_pending_heading_sections(sections, pending_heading_sections)
                if attached:
                    pending_heading_sections = []
                    pending_heading_block = None

            trailing_sections = self._pop_trailing_heading_only_sections(sections)
            buffer_sections(block, sections)

            if trailing_sections:
                if pending_heading_sections and pending_heading_block:
                    buffer_sections(pending_heading_block, pending_heading_sections)
                pending_heading_sections = trailing_sections
                pending_heading_block = block

        if pending_heading_sections and pending_heading_block:
            buffer_sections(pending_heading_block, pending_heading_sections)
        flush_buffer()

        return chunks

    @classmethod
    def _remove_repeated_page_boilerplate(cls, parsed_blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        repeated_lines = cls._detect_repeated_page_boilerplate_lines(parsed_blocks)
        if not repeated_lines:
            return parsed_blocks

        filtered_blocks: list[ParsedBlock] = []
        for block in parsed_blocks:
            if block.page_no is None or block.chunk_type != "text":
                filtered_blocks.append(block)
                continue

            lines = block.text.splitlines()
            kept_lines: list[str] = []
            removed_count = 0
            for line_index, raw_line in enumerate(lines):
                line = raw_line.strip()
                if line and cls._is_repeated_boilerplate_position(line_index, len(lines), line):
                    normalized = cls._normalize_repeated_boilerplate_line(line)
                    if normalized in repeated_lines:
                        removed_count += 1
                        continue
                kept_lines.append(raw_line)

            if removed_count == 0:
                filtered_blocks.append(block)
                continue

            metadata = dict(block.metadata)
            metadata["_filtered_repeated_page_boilerplate_lines"] = removed_count
            filtered_blocks.append(
                ParsedBlock(
                    text="\n".join(kept_lines).strip(),
                    chunk_type=block.chunk_type,
                    section_title=block.section_title,
                    page_no=block.page_no,
                    sheet_name=block.sheet_name,
                    row_start=block.row_start,
                    row_end=block.row_end,
                    metadata=metadata,
                )
            )

        return filtered_blocks

    @classmethod
    def _detect_repeated_page_boilerplate_lines(cls, parsed_blocks: list[ParsedBlock]) -> set[str]:
        page_blocks = [block for block in parsed_blocks if block.page_no is not None and block.chunk_type == "text"]
        page_count = len({block.page_no for block in page_blocks})
        if page_count < 2:
            return set()

        line_pages: dict[str, set[int]] = {}
        for block in page_blocks:
            lines = block.text.splitlines()
            for line_index, raw_line in enumerate(lines):
                line = raw_line.strip()
                if not line or not cls._is_repeated_boilerplate_position(line_index, len(lines), line):
                    continue
                normalized = cls._normalize_repeated_boilerplate_line(line)
                if not normalized or not cls._is_repeated_boilerplate_candidate(normalized):
                    continue
                line_pages.setdefault(normalized, set()).add(int(block.page_no))

        min_pages = 2 if page_count <= 3 else max(2, int(page_count * 0.4))
        return {line for line, pages in line_pages.items() if len(pages) >= min_pages}

    @classmethod
    def _is_repeated_boilerplate_position(cls, line_index: int, line_count: int, line: str) -> bool:
        if cls._looks_like_page_boilerplate_lines([line]):
            return True
        return line_index < REPEATED_BOILERPLATE_EDGE_LINES or line_index >= line_count - REPEATED_BOILERPLATE_EDGE_LINES

    @classmethod
    def _is_repeated_boilerplate_candidate(cls, line: str) -> bool:
        if len(line) > REPEATED_BOILERPLATE_MAX_CHARS:
            return False
        if cls._is_page_marker(line) or cls._is_toc_entry(line) or cls._is_numeric_value_line(line):
            return False
        return True

    @staticmethod
    def _normalize_repeated_boilerplate_line(line: str) -> str:
        return re.sub(r"\s+", "", line.strip(" \t\r\n-—–_·.。|｜"))

    @classmethod
    def _merge_small_continuation_sections(
        cls,
        sections: list[StructuralSection],
        *,
        max_chars: int,
    ) -> list[StructuralSection]:
        if len(sections) < 2:
            return sections

        merged: list[StructuralSection] = []
        for section in sections:
            if (
                merged
                and cls._is_soft_continuation_heading(section)
                and len(merged[-1].text) + len(section.text) + 1 <= max_chars
            ):
                merged[-1] = cls._merge_structural_sections(merged[-1], section)
            else:
                merged.append(section)
        return merged

    @classmethod
    def _merge_small_related_numbered_sections(
        cls,
        sections: list[StructuralSection],
        *,
        max_chars: int,
    ) -> list[StructuralSection]:
        if len(sections) < 2:
            return sections

        merged: list[StructuralSection] = []
        for section in sections:
            if (
                merged
                and cls._can_merge_small_related_numbered_sections(merged[-1], section, max_chars)
            ):
                merged[-1] = cls._merge_structural_sections(merged[-1], section)
            else:
                merged.append(section)
        return merged

    @classmethod
    def _can_merge_small_related_numbered_sections(
        cls,
        left: StructuralSection,
        right: StructuralSection,
        max_chars: int,
    ) -> bool:
        if cls._is_heading_only_section(left) or cls._is_heading_only_section(right):
            return False
        left_path = cls._heading_number_path(left.heading or cls._first_line(left.text))
        right_path = cls._heading_number_path(right.heading or cls._first_line(right.text))
        if not left_path or not right_path:
            return False
        if not cls._are_related_numbered_paths(left_path, right_path):
            return False
        merged_chars = len(left.text) + len(right.text) + 1
        if merged_chars > max_chars:
            return False
        compact_limit = max(160, int(max_chars * 0.25))
        if len(left_path) == len(right_path):
            if len(left_path) < 3:
                return False
            return len(left.text) <= compact_limit and len(right.text) <= compact_limit
        return len(left.text) <= compact_limit or len(right.text) <= compact_limit

    @staticmethod
    def _first_line(text: str) -> str:
        return next((line.strip() for line in text.splitlines() if line.strip()), "")

    @staticmethod
    def _heading_number_path(line: str) -> tuple[int, ...] | None:
        matches = re.findall(r"(?:^|>\s*)(\d{1,2}(?:[.．]\d{1,2}){0,5})", line.strip())
        if not matches:
            return None
        return tuple(int(part) for part in matches[-1].replace("．", ".").split("."))

    @staticmethod
    def _are_related_numbered_paths(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
        if len(left) == len(right):
            return len(left) > 1 and left[:-1] == right[:-1]
        if len(right) == len(left) + 1:
            return right[:-1] == left
        return False

    @classmethod
    def _can_merge_cross_page_continuation(
        cls,
        previous_block: ParsedBlock,
        previous_section: StructuralSection,
        current_block: ParsedBlock,
        current_section: StructuralSection,
        max_chars: int,
    ) -> bool:
        if previous_block.chunk_type != current_block.chunk_type:
            return False
        if previous_block.page_no is None or current_block.page_no is None:
            return False
        if current_block.page_no != previous_block.page_no + 1:
            return False
        if not previous_section.heading or not cls._is_numbered_section_heading(previous_section.heading):
            return False
        if not cls._is_soft_continuation_heading(current_section):
            return False
        return len(previous_section.text) + len(current_section.text) + 1 <= max_chars

    @staticmethod
    def _merge_structural_sections(left: StructuralSection, right: StructuralSection) -> StructuralSection:
        return StructuralSection(
            text=f"{left.text}\n{right.text}".strip(),
            heading=left.heading,
            heading_level=left.heading_level,
            start_line=left.start_line,
            end_line=right.end_line,
            split_reason=left.split_reason,
        )

    @classmethod
    def _is_soft_continuation_heading(cls, section: StructuralSection) -> bool:
        lines = [line.strip() for line in section.text.splitlines() if line.strip()]
        if not lines:
            return False
        first_line = lines[0]
        if cls._is_numbered_section_heading(first_line):
            return False
        return bool(re.match(r"^(?:场景|示例|案例)[一二三四五六七八九十\d]+[:：]?$", first_line)) or bool(
            re.match(r"^\d+[、)]", first_line)
        )

    @staticmethod
    def _is_numbered_section_heading(line: str) -> bool:
        return bool(re.match(r"^\d{1,2}(?:[.．]\d{1,2}){0,5}(?:\s+|[.．])", line.strip()))

    @classmethod
    def _split_structural_block(cls, text: str) -> list[StructuralSection]:
        lines = [(index, line.strip()) for index, line in enumerate(text.splitlines(), start=1) if line.strip()]
        if not lines:
            stripped = text.strip()
            return [StructuralSection(text=stripped, split_reason="empty_fallback")] if stripped else []

        toc_sections = cls._split_table_of_contents_block(lines)
        if toc_sections:
            return toc_sections

        sections: list[StructuralSection] = []
        current_lines: list[str] = []
        current_heading: str | None = None
        current_heading_level: int | None = None
        current_start_line: int | None = None
        current_reason = "paragraph"

        def flush(end_line: int | None = None) -> None:
            nonlocal current_lines, current_heading, current_heading_level, current_start_line, current_reason
            section_text = "\n".join(line for line in current_lines if line).strip()
            if section_text:
                sections.append(
                    StructuralSection(
                        text=section_text,
                        heading=current_heading,
                        heading_level=current_heading_level,
                        start_line=current_start_line,
                        end_line=end_line,
                        split_reason=current_reason,
                    )
                )
            current_lines = []
            current_heading = None
            current_heading_level = None
            current_start_line = None
            current_reason = "paragraph"

        previous_line_number: int | None = None
        for line_number, line in lines:
            heading = cls._detect_heading(line)
            if heading and current_lines:
                if not cls._is_heading_prefix_only(current_lines):
                    if previous_line_number and cls._has_trailing_page_marker_after_boilerplate(current_lines):
                        page_marker = current_lines[-1]
                        current_lines = current_lines[:-1]
                        flush(previous_line_number - 1)
                        current_lines = [page_marker]
                        current_start_line = previous_line_number
                    else:
                        flush(previous_line_number)

            if not current_lines:
                current_start_line = line_number

            if heading:
                current_heading, current_heading_level = heading
                current_reason = "heading"
            current_lines.append(line)
            previous_line_number = line_number

        flush(previous_line_number)
        sections = cls._merge_heading_only_sections(sections)

        if len(sections) == 1 and not sections[0].heading:
            paragraph_sections = cls._split_paragraph_sections(text)
            if len(paragraph_sections) > 1:
                return paragraph_sections

        return sections

    @classmethod
    def _split_table_of_contents_block(cls, lines: list[tuple[int, str]]) -> list[StructuralSection] | None:
        toc_entry_count = sum(1 for _, line in lines if cls._is_toc_entry(line))
        if toc_entry_count < 3:
            return None

        toc_title_positions = [position for position, (_, line) in enumerate(lines) if cls._is_toc_title(line)]
        entry_ratio = toc_entry_count / max(len(lines), 1)
        if not toc_title_positions and entry_ratio < 0.5:
            return None

        toc_start_position = toc_title_positions[0] if toc_title_positions else next(
            position for position, (_, line) in enumerate(lines) if cls._is_toc_entry(line)
        )
        for position in range(toc_start_position - 1, -1, -1):
            if cls._is_page_marker(lines[position][1]):
                toc_start_position = position
                break

        prefix_lines = lines[:toc_start_position]
        toc_lines = lines[toc_start_position:]
        if prefix_lines and not cls._looks_like_page_boilerplate_lines([line for _, line in prefix_lines]):
            toc_lines = lines
            prefix_lines = []

        sections: list[StructuralSection] = []
        if prefix_lines:
            sections.append(
                StructuralSection(
                    text="\n".join(line for _, line in prefix_lines).strip(),
                    start_line=prefix_lines[0][0],
                    end_line=prefix_lines[-1][0],
                    split_reason="paragraph",
                )
            )

        sections.append(
            StructuralSection(
                text="\n".join(line for _, line in toc_lines).strip(),
                heading="目录",
                heading_level=1,
                start_line=toc_lines[0][0],
                end_line=toc_lines[-1][0],
                split_reason="table_of_contents",
            )
        )
        return sections

    @classmethod
    def _merge_heading_only_sections(cls, sections: list[StructuralSection]) -> list[StructuralSection]:
        merged: list[StructuralSection] = []
        pending: list[StructuralSection] = []

        for section in sections:
            if cls._is_heading_only_section(section):
                pending.append(section)
                continue

            if pending:
                heading_path = [item.heading for item in pending if item.heading]
                if section.heading:
                    heading_path.append(section.heading)
                heading_prefix = "\n".join(item.text for item in pending)
                merged.append(
                    StructuralSection(
                        text=f"{heading_prefix}\n{section.text}".strip(),
                        heading=" > ".join(heading_path) if heading_path else section.heading,
                        heading_level=pending[0].heading_level,
                        start_line=pending[0].start_line,
                        end_line=section.end_line,
                        split_reason="heading",
                    )
                )
                pending = []
            else:
                merged.append(section)

        merged.extend(pending)
        return merged

    @classmethod
    def _is_heading_only_section(cls, section: StructuralSection) -> bool:
        lines = [line.strip() for line in section.text.splitlines() if line.strip()]
        return bool(section.heading and len(lines) == 1 and cls._detect_heading(lines[0]))

    @classmethod
    def _pop_trailing_heading_only_sections(cls, sections: list[StructuralSection]) -> list[StructuralSection]:
        trailing: list[StructuralSection] = []
        while sections and cls._is_heading_only_section(sections[-1]):
            trailing.insert(0, sections.pop())
        return trailing

    @classmethod
    def _prepend_pending_heading_sections(
        cls,
        sections: list[StructuralSection],
        pending: list[StructuralSection],
    ) -> bool:
        if not sections:
            return False

        attach_index = cls._find_pending_heading_attach_index(sections)
        if attach_index is None:
            return False

        target = sections[attach_index]
        heading_path = [section.heading for section in pending if section.heading]
        if target.heading:
            heading_path.append(target.heading)
        pending_text = "\n".join(section.text for section in pending if section.text).strip()
        sections[attach_index] = StructuralSection(
            text=f"{pending_text}\n{target.text}".strip(),
            heading=" > ".join(heading_path) if heading_path else target.heading,
            heading_level=pending[0].heading_level,
            start_line=pending[0].start_line,
            end_line=target.end_line,
            split_reason="heading",
        )
        return True

    @classmethod
    def _find_pending_heading_attach_index(cls, sections: list[StructuralSection]) -> int | None:
        for index, section in enumerate(sections):
            if cls._is_page_boilerplate_section(section):
                continue
            if section.split_reason == "table_of_contents":
                continue
            return index
        return None

    @staticmethod
    def _can_attach_pending_heading(previous_block: ParsedBlock, current_block: ParsedBlock) -> bool:
        if previous_block.chunk_type != current_block.chunk_type:
            return False
        if previous_block.page_no is None or current_block.page_no is None:
            return False
        return current_block.page_no == previous_block.page_no + 1

    @staticmethod
    def _split_paragraph_sections(text: str) -> list[StructuralSection]:
        sections: list[StructuralSection] = []
        current: list[str] = []
        current_start_line: int | None = None

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if line:
                if not current:
                    current_start_line = line_number
                current.append(line)
                continue
            if current:
                sections.append(
                    StructuralSection(
                        text="\n".join(current),
                        start_line=current_start_line,
                        end_line=line_number - 1,
                        split_reason="paragraph",
                    )
                )
                current = []
                current_start_line = None

        if current:
            sections.append(
                StructuralSection(
                    text="\n".join(current),
                    start_line=current_start_line,
                    end_line=len(text.splitlines()),
                    split_reason="paragraph",
                )
            )

        return sections

    @classmethod
    def _detect_heading(cls, line: str) -> tuple[str, int] | None:
        stripped = line.strip()
        if not stripped or len(stripped) > HEADING_MAX_CHARS:
            return None
        if cls._is_page_marker(stripped) or cls._is_toc_entry(stripped) or cls._is_numeric_value_line(stripped):
            return None

        markdown = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if markdown:
            return markdown.group(2).strip(), len(markdown.group(1))

        numbered = re.match(
            r"^((?:第[一二三四五六七八九十百千万\d]+[章节条部分篇])|(?:[一二三四五六七八九十]+、)|(?:\d{1,2}(?:[.．]\d{1,2}){0,5}[.．])|(?:\d{1,2}(?:[.．]\d{1,2}){0,5}\s+))\s*(.+)$",
            stripped,
        )
        if numbered:
            level = cls._numbered_heading_level(numbered.group(1))
            return stripped, level

        if stripped.endswith(("：", ":")) and len(stripped) <= 40:
            return stripped.rstrip("：:"), 3

        return None

    @staticmethod
    def _numbered_heading_level(prefix: str) -> int:
        number_path = re.match(r"\d{1,2}(?:[.．]\d{1,2})*", prefix.strip())
        if not number_path:
            return 1
        normalized = number_path.group(0).replace("．", ".")
        return min(normalized.count(".") + 1, 6)

    @staticmethod
    def _is_page_marker(line: str) -> bool:
        return bool(re.match(r"^\d+\s*/\s*\d+$", line.strip()))

    @staticmethod
    def _is_toc_title(line: str) -> bool:
        return bool(re.match(r"^目\s*录$", line.strip()))

    @staticmethod
    def _is_toc_entry(line: str) -> bool:
        stripped = line.strip()
        return bool(re.search(r"[.．·・…]{4,}\s*\d+\s*$", stripped))

    @staticmethod
    def _is_numeric_value_line(line: str) -> bool:
        stripped = line.strip()
        return bool(
            re.match(
                r"^\d+(?:,\d{3})*(?:\.\d+)?\s*(?:元|万元|%|％|天|个月|月|年|人|城|分|公里|km|KM)(?:[/／][A-Za-z0-9一-龥%％]+)?$",
                stripped,
            )
        )

    @classmethod
    def _is_heading_prefix_only(cls, lines: list[str]) -> bool:
        return bool(lines) and all(cls._is_page_marker(line) for line in lines)

    @staticmethod
    def _looks_like_page_boilerplate_lines(lines: list[str]) -> bool:
        text = "\n".join(lines)
        return "知识产权归属" in text or "未经授权许可" in text

    @classmethod
    def _is_page_boilerplate_section(cls, section: StructuralSection) -> bool:
        return section.split_reason == "paragraph" and cls._looks_like_page_boilerplate_lines(section.text.splitlines())

    @classmethod
    def _has_trailing_page_marker_after_boilerplate(cls, lines: list[str]) -> bool:
        return len(lines) > 1 and cls._is_page_marker(lines[-1]) and cls._looks_like_page_boilerplate_lines(lines[:-1])


class TableAwareChunkingStrategy:
    name = "table-aware"
    params_schema = {
        "type": "object",
        "properties": {
            "max_chars": {"type": "integer", "default": 1200, "minimum": 100, "maximum": 8000},
            "overlap_chars": {"type": "integer", "default": 150, "minimum": 0, "maximum": 2000},
            "table_rows_per_chunk": {"type": "integer", "default": 20, "minimum": 1, "maximum": 500},
        },
    }

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        fallback = FixedChunkingStrategy()
        chunks: list[ChunkPayload] = []
        chunk_index = 0

        for block in parsed_blocks:
            if block.chunk_type != "table":
                for payload in fallback.build_chunks([block], options=options):
                    payload.chunk_index = chunk_index
                    payload.metadata_json["chunking_strategy"] = self.name
                    payload.metadata_json["table_aware_fallback"] = True
                    chunks.append(payload)
                    chunk_index += 1
                continue

            rows = [row.strip() for row in block.text.splitlines() if row.strip()]
            if not rows:
                continue

            header = rows[0]
            table_rows = block.metadata.get("_table_rows")
            headers = block.metadata.get("headers") or []
            if table_rows and self._looks_like_faq_table(headers):
                row_batches = self._build_structured_row_batches(
                    table_rows=table_rows,
                    table_rows_per_chunk=options.table_rows_per_chunk,
                    max_chars=options.max_chars,
                )
                for batch_index, batch_info in enumerate(row_batches, start=1):
                    metadata = _clean_metadata(block.metadata)
                    metadata["chunking_strategy"] = self.name
                    metadata["table_batch"] = batch_index
                    metadata["table_batch_total"] = len(row_batches)
                    metadata["table_render_mode"] = "faq"
                    if batch_info.get("group_key"):
                        metadata["table_group_key"] = batch_info["group_key"]
                    chunk_text = self._render_faq_chunk(batch_info["raw_rows"])
                    batch_row_numbers = batch_info["row_numbers"]
                    chunks.append(
                        _build_chunk_payload(
                            chunk_index,
                            block,
                            chunk_text,
                            metadata,
                            row_start=batch_row_numbers[0] if batch_row_numbers else block.row_start,
                            row_end=batch_row_numbers[-1] if batch_row_numbers else block.row_end,
                        )
                    )
                    chunk_index += 1
                continue

            if table_rows:
                row_batches = self._build_structured_row_batches(
                    table_rows=table_rows,
                    table_rows_per_chunk=options.table_rows_per_chunk,
                    max_chars=options.max_chars,
                )
            else:
                data_rows = rows[1:]
                if not data_rows:
                    data_rows = [header]
                row_batches = self._build_row_batches(
                    header=header,
                    data_rows=data_rows,
                    row_numbers=block.metadata.get("_row_numbers"),
                    table_rows_per_chunk=options.table_rows_per_chunk,
                    max_chars=options.max_chars,
                )
            for batch_index, batch_info in enumerate(row_batches, start=1):
                metadata = _clean_metadata(block.metadata)
                metadata["chunking_strategy"] = self.name
                metadata["table_header"] = header
                metadata["table_batch"] = batch_index
                metadata["table_batch_total"] = len(row_batches)
                metadata["table_render_mode"] = "plain"
                if batch_info.get("group_key"):
                    metadata["table_group_key"] = batch_info["group_key"]
                batch_rows = batch_info["rows"]
                chunk_text = "\n".join([header, *batch_rows]) if batch_rows != [header] else header
                batch_row_numbers = batch_info["row_numbers"]
                chunks.append(
                    _build_chunk_payload(
                        chunk_index,
                        block,
                        chunk_text,
                        metadata,
                        row_start=batch_row_numbers[0] if batch_row_numbers else block.row_start,
                        row_end=batch_row_numbers[-1] if batch_row_numbers else block.row_end,
                    )
                )
                chunk_index += 1

        return chunks

    @staticmethod
    def _build_row_batches(
        *,
        header: str,
        data_rows: list[str],
        row_numbers: list[int] | None,
        table_rows_per_chunk: int,
        max_chars: int,
    ) -> list[dict[str, list]]:
        batches: list[dict[str, list]] = []
        current_batch: list[str] = []
        current_row_numbers: list[int] = []
        current_chars = len(header)
        effective_row_numbers = row_numbers or list(range(1, len(data_rows) + 1))

        for row, row_number in zip(data_rows, effective_row_numbers, strict=False):
            row_chars = len(row) + 1
            exceeds_row_limit = len(current_batch) >= table_rows_per_chunk
            exceeds_char_limit = bool(current_batch) and (current_chars + row_chars > max_chars)

            if exceeds_row_limit or exceeds_char_limit:
                batches.append({"rows": current_batch, "row_numbers": current_row_numbers})
                current_batch = []
                current_row_numbers = []
                current_chars = len(header)

            current_batch.append(row)
            current_row_numbers.append(row_number)
            current_chars += row_chars

        if current_batch:
            batches.append({"rows": current_batch, "row_numbers": current_row_numbers})

        return batches

    @classmethod
    def _build_structured_row_batches(
        cls,
        *,
        table_rows: list[dict[str, object]],
        table_rows_per_chunk: int,
        max_chars: int,
    ) -> list[dict[str, list]]:
        grouped_rows: list[dict[str, object]] = []
        current_group_rows: list[dict[str, object]] = []
        current_group_key: tuple[str, ...] | None = None

        for row in table_rows:
            raw_group_key = row.get("group_key") or []
            group_key = tuple(str(item) for item in raw_group_key if item)
            if current_group_rows and group_key != current_group_key:
                grouped_rows.append({"group_key": current_group_key or tuple(), "rows": current_group_rows})
                current_group_rows = []
            current_group_rows.append(row)
            current_group_key = group_key

        if current_group_rows:
            grouped_rows.append({"group_key": current_group_key or tuple(), "rows": current_group_rows})

        batches: list[dict[str, list]] = []
        for group in grouped_rows:
            group_rows = group["rows"]
            group_batches = cls._split_group_rows(
                group_rows=group_rows,
                table_rows_per_chunk=table_rows_per_chunk,
                max_chars=max_chars,
            )
            for batch in group_batches:
                batch["group_key"] = list(group["group_key"])
                batches.append(batch)

        return batches

    @staticmethod
    def _split_group_rows(
        *,
        group_rows: list[dict[str, object]],
        table_rows_per_chunk: int,
        max_chars: int,
    ) -> list[dict[str, list]]:
        batches: list[dict[str, list]] = []
        current_rows: list[str] = []
        current_row_numbers: list[int] = []
        current_raw_rows: list[dict[str, object]] = []
        current_chars = 0

        for row in group_rows:
            row_text = str(row["text"])
            row_number = int(row["row_number"])
            row_chars = len(row_text)
            exceeds_row_limit = len(current_rows) >= table_rows_per_chunk
            exceeds_char_limit = bool(current_rows) and (current_chars + row_chars > max_chars)

            if exceeds_row_limit or exceeds_char_limit:
                batches.append({"rows": current_rows, "row_numbers": current_row_numbers, "raw_rows": current_raw_rows})
                current_rows = []
                current_row_numbers = []
                current_raw_rows = []
                current_chars = 0

            current_rows.append(row_text)
            current_row_numbers.append(row_number)
            current_raw_rows.append(row)
            current_chars += row_chars

        if current_rows:
            batches.append({"rows": current_rows, "row_numbers": current_row_numbers, "raw_rows": current_raw_rows})

        return batches

    @staticmethod
    def _looks_like_faq_table(headers: list[str]) -> bool:
        header_set = {str(header).strip() for header in headers}
        full_faq_headers = {"一级", "二级", "三级", "四级"}
        compact_faq_headers = {"一级", "二级", "三级"}
        return full_faq_headers.issubset(header_set) or compact_faq_headers.issubset(header_set)

    @staticmethod
    def _render_faq_chunk(raw_rows: list[dict[str, object]]) -> str:
        sections: list[str] = []
        for row in raw_rows:
            fields = row.get("fields") or {}
            if not isinstance(fields, dict):
                continue
            similar_questions = row.get("similar_questions") or []
            group_key = row.get("group_key") or []
            has_grouping = bool(group_key)
            if fields.get("四级"):
                title = str(fields.get("三级") or fields.get("二级") or "未命名问题")
                answer = str(fields.get("四级") or "")
                level_one = str(fields.get("一级") or "")
                level_two = str(fields.get("二级") or "")
            else:
                if has_grouping:
                    title = str(fields.get("二级") or fields.get("一级") or "未命名问题")
                    level_one = str(fields.get("一级") or "")
                    level_two = str(fields.get("二级") or "")
                else:
                    title = str(fields.get("一级") or fields.get("二级") or "未命名问题")
                    level_one = ""
                    level_two = ""
                answer = str(fields.get("三级") or "")
            lines = [f"问题：{title}"]
            if level_one:
                lines.append(f"一级分类：{level_one}")
            if level_two:
                lines.append(f"二级分类：{level_two}")
            if answer:
                lines.append(f"答案：{answer}")
            if not has_grouping and not similar_questions and fields.get("二级"):
                lines.append(f"补充信息：{fields['二级']}")
            if similar_questions:
                lines.append("相似问法：" + "；".join(str(item) for item in similar_questions if item))
            sections.append("\n".join(lines))
        return "\n\n".join(section for section in sections if section)


class ParentChildChunkingStrategy:
    """Parent-child chunking strategy.

    Parent chunks: 2000-4000 chars for broader context retrieval.
    Child chunks: 500-800 chars for granular embedding.
    Only child chunks get embedded; retrieval returns parent context_text.
    """

    name = "parent-child"
    params_schema = {
        "type": "object",
        "properties": {
            "parent_max_chars": {"type": "integer", "default": 3000, "minimum": 1000, "maximum": 8000},
            "child_max_chars": {"type": "integer", "default": 600, "minimum": 200, "maximum": 2000},
            "overlap_chars": {"type": "integer", "default": 100, "minimum": 0, "maximum": 1000},
        },
    }

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        parent_max = getattr(options, "parent_max_chars", 3000)
        child_max = getattr(options, "child_max_chars", 600)
        overlap = getattr(options, "overlap_chars", 100)

        chunks: list[ChunkPayload] = []
        chunk_index = 0
        parsed_blocks = StructuralChunkingStrategy._remove_repeated_page_boilerplate(parsed_blocks)
        parent_sources = self._build_document_parent_sources(
            parsed_blocks,
            parent_max=max(parent_max, child_max),
            overlap=max(overlap, 0),
        )

        parent_total = len(parent_sources)
        for parent_idx, parent_source in enumerate(parent_sources):
            block = parent_source.block
            parent_segment = parent_source.segment
            parent_uuid = str(uuid.uuid4())
            parent_text = parent_segment.text
            children = split_text(parent_text, max_chars=child_max, overlap_chars=min(overlap, child_max // 2))

            for child_idx, child_text in enumerate(children):
                metadata = _clean_metadata(block.metadata)
                metadata["chunking_strategy"] = self.name
                metadata.update(parent_segment.metadata)
                metadata["parent_index"] = parent_idx
                metadata["parent_total"] = parent_total
                metadata["child_index"] = child_idx
                metadata["child_total"] = len(children)
                metadata["total_children_in_parent"] = len(children)
                metadata["parent_char_count"] = len(parent_text)
                metadata["child_char_count"] = len(child_text)

                chunks.append(
                    ChunkPayload(
                        chunk_index=chunk_index,
                        chunk_text=child_text,
                        chunk_type=block.chunk_type,
                        section_title=block.section_title,
                        page_no=block.page_no,
                        sheet_name=block.sheet_name,
                        row_start=block.row_start,
                        row_end=block.row_end,
                        token_count=estimate_token_count(child_text),
                        char_count=len(child_text),
                        metadata_json=metadata,
                        parent_chunk_uuid=parent_uuid,
                        chunk_group_uuid=parent_source.group_uuid,
                        chunk_level="child",
                        context_text=parent_text,
                    )
                )
                chunk_index += 1

        return chunks

    @classmethod
    def _build_document_parent_sources(
        cls,
        parsed_blocks: list[ParsedBlock],
        *,
        parent_max: int,
        overlap: int,
    ) -> list[ParentSegmentSource]:
        parent_sources: list[ParentSegmentSource] = []
        current_sections: list[ParentSectionSource] = []
        current_chars = 0
        text_section_index = 0

        def section_length(section: StructuralSection) -> int:
            return len(section.text) + (2 if current_sections else 0)

        def flush(reason: str = "structural_group") -> None:
            nonlocal current_sections, current_chars
            if not current_sections:
                return

            text = "\n\n".join(source.section.text for source in current_sections).strip()
            headings = [source.section.heading for source in current_sections if source.section.heading]
            pages = [source.block.page_no for source in current_sections if source.block.page_no is not None]
            first_source = current_sections[0]
            metadata = {
                "parent_split_reason": reason,
                "parent_section_start": current_sections[0].section_index,
                "parent_section_end": current_sections[-1].section_index,
                "parent_section_count": len(current_sections),
                "parent_section_heading": " > ".join(headings) if headings else first_source.block.section_title,
                "parent_block_count": len({id(source.block) for source in current_sections}),
            }
            if pages:
                metadata["parent_page_start"] = min(pages)
                metadata["parent_page_end"] = max(pages)

            parent_sources.append(
                ParentSegmentSource(
                    block=first_source.block,
                    group_uuid=str(uuid.uuid4()),
                    segment=ParentSegment(text=text, metadata=metadata),
                )
            )
            current_sections = []
            current_chars = 0

        for block in parsed_blocks:
            if block.chunk_type != "text":
                flush()
                parent_sources.extend(
                    ParentSegmentSource(block=block, group_uuid=str(uuid.uuid4()), segment=parent_segment)
                    for parent_segment in cls._build_parent_segments(block, parent_max=parent_max, overlap=overlap)
                )
                continue

            sections = StructuralChunkingStrategy._split_structural_block(block.text)
            if not sections:
                continue

            for section_index, section in enumerate(sections, start=1):
                text_section_index += 1
                if len(section.text) > parent_max:
                    flush()
                    parts = split_text(section.text, max_chars=parent_max, overlap_chars=overlap)
                    for part_index, part in enumerate(parts, start=1):
                        metadata = {
                            "parent_split_reason": "oversized_section",
                            "parent_section_start": text_section_index,
                            "parent_section_end": text_section_index,
                            "parent_section_count": 1,
                            "parent_section_heading": section.heading or block.section_title,
                            "parent_split_part": part_index,
                            "parent_split_total": len(parts),
                            "parent_block_count": 1,
                        }
                        if block.page_no is not None:
                            metadata["parent_page_start"] = block.page_no
                            metadata["parent_page_end"] = block.page_no
                        parent_sources.append(
                            ParentSegmentSource(
                                block=block,
                                group_uuid=str(uuid.uuid4()),
                                segment=ParentSegment(text=part, metadata=metadata),
                            )
                    )
                    continue

                next_chars = current_chars + section_length(section)
                if current_sections and next_chars > parent_max:
                    flush()
                    next_chars = len(section.text)

                current_sections.append(ParentSectionSource(block=block, section_index=text_section_index, section=section))
                current_chars = next_chars

        flush()
        parent_total = len(parent_sources)
        for parent_index, parent_source in enumerate(parent_sources, start=1):
            parent_source.segment.metadata.setdefault("parent_split_part", parent_index)
            parent_source.segment.metadata["parent_split_total"] = parent_total
        return parent_sources

    @classmethod
    def _build_parent_segments(
        cls,
        block: ParsedBlock,
        *,
        parent_max: int,
        overlap: int,
    ) -> list[ParentSegment]:
        if block.chunk_type == "table":
            parts = split_text(block.text, max_chars=parent_max, overlap_chars=overlap)
            return [
                ParentSegment(
                    text=part,
                    metadata={
                        "parent_split_reason": "table_block",
                        "parent_split_part": index,
                        "parent_split_total": len(parts),
                    },
                )
                for index, part in enumerate(parts, start=1)
            ]

        sections = StructuralChunkingStrategy._split_structural_block(block.text)
        if not sections:
            return []

        parents: list[ParentSegment] = []
        current_sections: list[tuple[int, StructuralSection]] = []
        current_chars = 0

        def section_length(section: StructuralSection) -> int:
            return len(section.text) + (2 if current_sections else 0)

        def flush(reason: str = "structural_group") -> None:
            nonlocal current_sections, current_chars
            if not current_sections:
                return
            text = "\n\n".join(section.text for _, section in current_sections).strip()
            headings = [section.heading for _, section in current_sections if section.heading]
            parents.append(
                ParentSegment(
                    text=text,
                    metadata={
                        "parent_split_reason": reason,
                        "parent_section_start": current_sections[0][0],
                        "parent_section_end": current_sections[-1][0],
                        "parent_section_count": len(current_sections),
                        "parent_section_heading": " > ".join(headings) if headings else block.section_title,
                    },
                )
            )
            current_sections = []
            current_chars = 0

        for section_index, section in enumerate(sections, start=1):
            if len(section.text) > parent_max:
                flush()
                parts = split_text(section.text, max_chars=parent_max, overlap_chars=overlap)
                for part_index, part in enumerate(parts, start=1):
                    parents.append(
                        ParentSegment(
                            text=part,
                            metadata={
                                "parent_split_reason": "oversized_section",
                                "parent_section_start": section_index,
                                "parent_section_end": section_index,
                                "parent_section_count": 1,
                                "parent_section_heading": section.heading or block.section_title,
                                "parent_split_part": part_index,
                                "parent_split_total": len(parts),
                            },
                        )
                    )
                continue

            next_chars = current_chars + section_length(section)
            if current_sections and next_chars > parent_max:
                flush()
                next_chars = len(section.text)

            current_sections.append((section_index, section))
            current_chars = next_chars

        flush()
        parent_total = len(parents)
        for parent_index, parent in enumerate(parents, start=1):
            parent.metadata.setdefault("parent_split_part", parent_index)
            parent.metadata["parent_split_total"] = parent_total
        return parents


class SemanticChunkingStrategy:
    """Semantic chunking strategy.

    Splits text at semantic boundaries using local embedding similarity.
    Falls back to structural chunking when >5000 sentences.
    """

    name = "semantic"
    params_schema = {
        "type": "object",
        "properties": {
            "min_chunk_sentences": {"type": "integer", "default": 3, "minimum": 1, "maximum": 50},
            "max_chunk_sentences": {"type": "integer", "default": 20, "minimum": 2, "maximum": 100},
            "similarity_threshold": {"type": "number", "default": 0.5, "minimum": 0.0, "maximum": 1.0},
            "merge_window": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
        },
    }

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        min_sentences = max(1, int(getattr(options, "min_chunk_sentences", 3)))
        max_sentences = max(min_sentences, int(getattr(options, "max_chunk_sentences", 20)))
        similarity_threshold = min(max(float(getattr(options, "similarity_threshold", 0.5)), 0.0), 1.0)
        merge_window = max(1, int(getattr(options, "merge_window", 3)))

        chunks: list[ChunkPayload] = []
        chunk_index = 0

        for block in parsed_blocks:
            sentences = self._split_sentences(block.text)
            if len(sentences) <= min_sentences:
                metadata = _clean_metadata(block.metadata)
                metadata["chunking_strategy"] = self.name
                metadata["semantic_segment_index"] = 1
                metadata["semantic_segment_total"] = 1
                metadata["sentence_start"] = 1 if sentences else 0
                metadata["sentence_end"] = len(sentences)
                metadata["sentence_count"] = len(sentences)
                metadata["semantic_split_reason"] = "minimum_sentence_count"
                chunks.append(_build_chunk_payload(chunk_index, block, block.text.strip(), metadata))
                chunk_index += 1
                continue

            if len(sentences) > 5000:
                fallback = StructuralChunkingStrategy()
                for payload in fallback.build_chunks([block], options=options):
                    payload.chunk_index = chunk_index
                    payload.metadata_json["chunking_strategy"] = self.name
                    payload.metadata_json["semantic_fallback"] = "structural"
                    chunks.append(payload)
                    chunk_index += 1
                continue

            breakpoints = self._detect_breakpoints(
                sentences,
                similarity_threshold=similarity_threshold,
                merge_window=merge_window,
            )

            segments = self._build_segments(sentences, breakpoints, min_sentences, max_sentences)

            for segment_index, segment in enumerate(segments, start=1):
                metadata = _clean_metadata(block.metadata)
                metadata["chunking_strategy"] = self.name
                metadata["semantic_segment_index"] = segment_index
                metadata["semantic_segment_total"] = len(segments)
                metadata["sentence_start"] = segment.sentence_start
                metadata["sentence_end"] = segment.sentence_end
                metadata["sentence_count"] = segment.sentence_end - segment.sentence_start + 1
                metadata["semantic_split_reason"] = segment.split_reason
                metadata["similarity_threshold"] = similarity_threshold
                metadata["merge_window"] = merge_window
                if segment.breakpoint_score is not None:
                    metadata["semantic_breakpoint_score"] = round(segment.breakpoint_score, 4)
                chunks.append(_build_chunk_payload(chunk_index, block, segment.text, metadata))
                chunk_index += 1

        return chunks

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        pattern = r"(?<=[。！？.!?\n])\s*"
        parts = re.split(pattern, text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _detect_breakpoints(
        sentences: list[str],
        *,
        similarity_threshold: float,
        merge_window: int,
    ) -> dict[int, float]:
        if len(sentences) < 2:
            return {}

        provider = SemanticChunkingStrategy._get_embedding_provider()

        vectors: list[list[float]] = []
        if provider:
            try:
                results = provider.embed_texts(sentences)
                vectors = [result.vector for result in results]
            except Exception:
                vectors = [SemanticChunkingStrategy._fallback_vector(sentence) for sentence in sentences]
        else:
            vectors = [SemanticChunkingStrategy._fallback_vector(sentence) for sentence in sentences]

        if len(vectors) < 2:
            return {}

        breakpoints: dict[int, float] = {}
        for index in range(len(vectors) - 1):
            left = SemanticChunkingStrategy._average_vectors(vectors[max(0, index + 1 - merge_window) : index + 1])
            right = SemanticChunkingStrategy._average_vectors(vectors[index + 1 : min(len(vectors), index + 1 + merge_window)])
            sim = SemanticChunkingStrategy._cosine_similarity(left, right)
            if sim < similarity_threshold:
                breakpoints[index + 1] = sim

        return breakpoints

    @staticmethod
    def _build_segments(
        sentences: list[str],
        breakpoints: dict[int, float],
        min_sentences: int,
        max_sentences: int,
    ) -> list[SemanticSegment]:
        segments: list[SemanticSegment] = []
        current: list[str] = []
        current_start = 0

        for index, sentence in enumerate(sentences):
            current.append(sentence)
            sentence_count = len(current)
            boundary = index + 1

            should_split = boundary in breakpoints and sentence_count >= min_sentences
            reached_max = sentence_count >= max_sentences
            if not should_split and not reached_max:
                continue

            split_reason = "semantic_breakpoint" if should_split else "max_sentence_limit"
            segments.append(
                SemanticSegment(
                    text=" ".join(current),
                    sentence_start=current_start + 1,
                    sentence_end=index + 1,
                    split_reason=split_reason,
                    breakpoint_score=breakpoints.get(boundary) if should_split else None,
                )
            )
            current = []
            current_start = index + 1

        if current:
            segments.append(
                SemanticSegment(
                    text=" ".join(current),
                    sentence_start=current_start + 1,
                    sentence_end=len(sentences),
                    split_reason="tail",
                )
            )

        return segments

    @staticmethod
    def _average_vectors(vectors: list[list[float]]) -> list[float]:
        if not vectors:
            return []
        width = max(len(vector) for vector in vectors)
        averaged: list[float] = []
        for index in range(width):
            values = [vector[index] for vector in vectors if index < len(vector)]
            averaged.append(sum(values) / len(values) if values else 0.0)
        return averaged

    @staticmethod
    def _get_embedding_provider():
        try:
            if get_settings is not None:
                settings = get_settings()
                return EmbeddingProvider(settings)
        except Exception:
            pass
        return None

    @staticmethod
    def _fallback_vector(text: str) -> list[float]:
        import hashlib

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw_values = list(digest)[:16]
        return [round(v / 255.0, 6) for v in raw_values]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class ChatRecordChunkingStrategy:
    """Chat record chunking strategy for WeCom (企业微信) chat export PDFs.

    Parses chat messages by speaker+timestamp pattern, merges quoted replies,
    detects topic breaks via time gaps, and groups messages into topic-based chunks.

    Designed for PDF exports from WeCom chat history. The format is:

        Page header (page 1 only):
            呼鹏琛 2026年05月24日 周日 02:12
            发件人 呼鹏琛<hupengchen@baihe.com>
            收件人 呼鹏琛<hupengchen@baihe.com>
            时间 2026年05月24日 周日 02:11
            季雪平和呼鹏琛的聊天记录

        Messages:
            季雪平 05-06 10:04
            亲，你看下姜晓玉...
            呼鹏琛 05-06 10:24
            我查下看看

        Quoted replies:
            呼鹏琛 05-06 10:52
            "季雪平：
            [图片]..."
            ------
            回复正文...

        Page footer:
            第X/Y页
    """

    name = "chat-record"
    params_schema = {
        "type": "object",
        "properties": {
            "max_chars": {"type": "integer", "default": 1500, "minimum": 300, "maximum": 8000},
            "overlap_chars": {"type": "integer", "default": 100, "minimum": 0, "maximum": 500},
            "topic_gap_minutes": {"type": "integer", "default": 60, "minimum": 5, "maximum": 1440},
            "merge_quoted_replies": {"type": "boolean", "default": True},
        },
    }

    _MSG_TIMESTAMP_RE = re.compile(r"^(.+?)\s+(\d{2}-\d{2})\s+(\d{2}:\d{2})$")
    _PAGE_FOOTER_RE = re.compile(r"^第\s*\d+\s*/\s*\d+\s*[⻚页页]$")
    _EXPORT_HEADER_RE = re.compile(
        r"^(?:发件[⼊人]|收件[⼊人]|时间)\s|^.+?\d{4}年\d{1,2}[⽉月]\d{1,2}[⽇日]"
    )
    _CHAT_TITLE_RE = re.compile(r"(.+?)和(.+?)的聊天记录")
    _SENDER_INFO_RE = re.compile(r"^(\S+)[PHP|JAVA|PYTHON|前端|后端|开发|⼯|工]")
    _EMPTY_CONTENT_RE = re.compile(r"^\[.+\]$")
    _SPEAKER_LINE_RE = re.compile(r"^[\u4e00-\u9fff]{2,5}$")
    _TIMESTAMP_LINE_RE = re.compile(r"^(\d{2})[- ](\d{2})\s+(\d{2}):(\d{2})$")
    _WECOM_EXPORT_DATE_RE = re.compile(r"\d{4}\s*年\d{1,2}[⽉月]\d{1,2}[⽇日]")
    _WECOM_HEADER_FIELD_RE = re.compile(r"^(?:发件[⼊人⼈]|收件[⼊人⼈]|时间)\s*$")
    _CN_QUOTE_OPEN_CHARS = frozenset({"\u201c", "\u2018", "\u300c", '"'})

    @staticmethod
    def _is_quote_start(line: str) -> bool:
        return any(line.startswith(c) for c in ChatRecordChunkingStrategy._CN_QUOTE_OPEN_CHARS)

        return result

    @staticmethod
    def _strip_cn_quotes(text: str) -> str:
        """Strip Chinese and ASCII quote characters from text boundaries."""
        result = text
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        if result.startswith("\u201c") and result.endswith("\u201d"):
            result = result[1:-1]
        elif result.startswith("\u201c") and result.count("\u201d") > 0:
            result = result[1 : result.rindex("\u201d")]
        if result.startswith("\u2018") and result.endswith("\u2019"):
            result = result[1:-1]
        if result.startswith("\u300c") and result.endswith("\u300d"):
            result = result[1:-1]
        return result

    def build_chunks(
        self,
        parsed_blocks: list[ParsedBlock],
        *,
        options: ChunkingOptions,
    ) -> list[ChunkPayload]:
        max_chars = max(300, int(getattr(options, "max_chars", 1500)))
        overlap_chars = max(0, int(getattr(options, "overlap_chars", 100)))
        topic_gap_minutes = max(5, int(getattr(options, "topic_gap_minutes", 60)))
        merge_quotes = bool(getattr(options, "merge_quoted_replies", True))

        clean_text, chat_metadata = self._clean_and_extract_metadata(parsed_blocks)
        if not clean_text.strip():
            return []

        messages = self._parse_messages(clean_text, merge_quotes=merge_quotes)
        if not messages:
            return []

        topics = self._group_into_topics(messages, gap_minutes=topic_gap_minutes)
        if not topics:
            return []

        chunks: list[ChunkPayload] = []
        chunk_index = 0

        for topic_index, topic_messages in enumerate(topics, start=1):
            topic_segments = self._split_oversized_topic(
                topic_messages,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
            for segment_index, segment in enumerate(topic_segments, start=1):
                segment_text = self._format_messages(segment)
                if not segment_text.strip():
                    continue

                metadata = dict(chat_metadata)
                metadata["chunking_strategy"] = self.name
                metadata["chat_topic_index"] = topic_index
                metadata["chat_topic_total"] = len(topics)
                metadata["chat_message_count"] = len(segment)
                metadata["chat_segment_index"] = segment_index
                metadata["chat_segment_total"] = len(topic_segments)
                metadata["chat_participants"] = list(
                    dict.fromkeys(msg.speaker for msg in segment)
                )
                if segment:
                    metadata["chat_time_start"] = segment[0].date_str + " " + segment[0].time_str
                    metadata["chat_time_end"] = segment[-1].date_str + " " + segment[-1].time_str
                metadata["chat_has_quoted_replies"] = any(
                    msg.quoted_speaker is not None for msg in segment
                )

                if parsed_blocks:
                    reference_block = parsed_blocks[0]
                else:
                    reference_block = ParsedBlock(text=segment_text)

                chunks.append(
                    _build_chunk_payload(chunk_index, reference_block, segment_text, metadata)
                )
                chunk_index += 1

        return chunks

    def _clean_and_extract_metadata(
        self, parsed_blocks: list[ParsedBlock]
    ) -> tuple[str, dict]:
        chat_metadata: dict = {
            "chat_source": "wecom_export",
        }

        all_lines: list[str] = []
        header_zone_ended = False
        saw_export_date = False

        for block in parsed_blocks:
            for idx, line in enumerate(block.text.splitlines()):
                stripped = line.strip()
                if not stripped:
                    continue

                if self._PAGE_FOOTER_RE.match(stripped):
                    continue

                if block.page_no == 1 and not header_zone_ended:
                    title_match = self._CHAT_TITLE_RE.match(stripped)
                    if title_match:
                        chat_metadata["chat_participant_a"] = title_match.group(1).strip()
                        chat_metadata["chat_participant_b"] = title_match.group(2).strip()
                        chat_metadata["chat_title"] = stripped
                        header_zone_ended = True
                        continue

                    if self._is_header_zone_line(stripped, saw_export_date):
                        if re.search(r"\d{4}年", stripped):
                            saw_export_date = True
                        continue

                all_lines.append(line)

        return "\n".join(all_lines), chat_metadata

    @classmethod
    def _is_header_zone_line(cls, line: str, saw_export_date: bool) -> bool:
        """Check if a line belongs to the WeCom export header zone."""
        if cls._WECOM_EXPORT_DATE_RE.search(line):
            return True
        if cls._WECOM_HEADER_FIELD_RE.match(line):
            return True
        if re.match(r"^\S+<[^>]+>\s*$", line):
            return True
        if re.match(r"^(?:百合佳缘|百合(.+)集团)$", line):
            return True
        if re.match(r"^(?:PHP|Java|Python|前端|后端|开发|运维|测试|产品|设计|[⼯工]程)师$", line):
            return True
        if re.match(r"^[\u4e00-\u9fff]{2,5}$", line):
            return True
        return False

    def _parse_messages(
        self, text: str, *, merge_quotes: bool = True
    ) -> list[ChatMessage]:
        lines = text.splitlines()
        messages: list[ChatMessage] = []
        i = 0
        total_lines = len(lines)

        def _is_new_message(line_idx: int) -> bool:
            if line_idx + 1 >= total_lines:
                return False
            speaker_line = lines[line_idx].strip()
            ts_line = lines[line_idx + 1].strip()
            if not self._SPEAKER_LINE_RE.match(speaker_line):
                return False
            if not self._TIMESTAMP_LINE_RE.match(ts_line):
                return False
            return True

        while i < total_lines:
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue

            if not _is_new_message(i):
                i += 1
                continue

            speaker = stripped
            date_str_raw = lines[i + 1].strip()
            ts_parts = self._TIMESTAMP_LINE_RE.match(date_str_raw)
            if not ts_parts:
                i += 1
                continue

            date_str = f"{ts_parts.group(1)}-{ts_parts.group(2)}"
            time_str = f"{ts_parts.group(3)}:{ts_parts.group(4)}"
            raw_lines = [lines[i], lines[i + 1]]
            i += 2

            content_lines: list[str] = []
            quoted_speaker: str | None = None
            quoted_content: str | None = None
            content_type = "text"
            in_quote = False
            quote_lines: list[str] = []

            while i < total_lines:
                next_stripped = lines[i].strip()

                if not next_stripped:
                    i += 1
                    continue

                if _is_new_message(i):
                    break

                if self._PAGE_FOOTER_RE.match(next_stripped):
                    i += 1
                    continue

                raw_lines.append(lines[i])

                if merge_quotes and content_type == "text" and not in_quote and not content_lines:
                    if self._is_quote_start(next_stripped):
                        in_quote = True
                        quote_lines = [next_stripped]
                        i += 1
                        continue

                if in_quote:
                    if next_stripped == "------" or next_stripped.startswith("------"):
                        in_quote = False
                        quote_text = "\n".join(quote_lines).strip()
                        quote_text = ChatRecordChunkingStrategy._strip_cn_quotes(quote_text)
                        colon_idx = quote_text.find("：")
                        if colon_idx < 0:
                            colon_idx = quote_text.find(":")
                        if colon_idx >= 0:
                            quoted_speaker = quote_text[:colon_idx].strip()
                            quoted_content = quote_text[colon_idx + 1:].strip()
                        else:
                            quoted_content = quote_text
                        content_type = "reply"
                        i += 1
                        continue
                    quote_lines.append(next_stripped)
                    i += 1
                    continue

                content_lines.append(next_stripped)
                i += 1

            content = "\n".join(content_lines).strip()

            if content and self._EMPTY_CONTENT_RE.match(content) and not quoted_speaker:
                content_type = "attachment"

            if not content and not quoted_speaker:
                continue

            messages.append(
                ChatMessage(
                    speaker=speaker,
                    date_str=date_str,
                    time_str=time_str,
                    content=content,
                    content_type=content_type,
                    quoted_speaker=quoted_speaker,
                    quoted_content=quoted_content,
                    raw_text="\n".join(raw_lines),
                )
            )

        return messages

    def _group_into_topics(
        self,
        messages: list[ChatMessage],
        *,
        gap_minutes: int = 60,
    ) -> list[list[ChatMessage]]:
        """Group messages into topics by time gaps and date breaks."""
        if not messages:
            return []

        topics: list[list[ChatMessage]] = []
        current_topic: list[ChatMessage] = [messages[0]]

        for i in range(1, len(messages)):
            prev = current_topic[-1]
            curr = messages[i]

            if curr.date_str != prev.date_str:
                topics.append(current_topic)
                current_topic = [curr]
                continue

            gap = self._time_gap_minutes(
                prev.date_str, prev.time_str, curr.date_str, curr.time_str
            )
            if gap >= gap_minutes:
                topics.append(current_topic)
                current_topic = [curr]
            else:
                current_topic.append(curr)

        if current_topic:
            topics.append(current_topic)

        return topics

    @staticmethod
    def _time_gap_minutes(date1: str, time1: str, date2: str, time2: str) -> int:
        """Calculate absolute time gap in minutes between two chat timestamps.

        Uses approximate month length (31 days) for relative comparison.
        """
        try:
            mon1, day1 = int(date1.split("-")[0]), int(date1.split("-")[1])
            mon2, day2 = int(date2.split("-")[0]), int(date2.split("-")[1])
            hr1, mn1 = int(time1.split(":")[0]), int(time1.split(":")[1])
            hr2, mn2 = int(time2.split(":")[0]), int(time2.split(":")[1])
        except (ValueError, IndexError):
            return 0

        total1 = mon1 * 31 * 24 * 60 + day1 * 24 * 60 + hr1 * 60 + mn1
        total2 = mon2 * 31 * 24 * 60 + day2 * 24 * 60 + hr2 * 60 + mn2
        return abs(total2 - total1)

    def _split_oversized_topic(
        self,
        messages: list[ChatMessage],
        *,
        max_chars: int,
        overlap_chars: int,
    ) -> list[list[ChatMessage]]:
        """Split an oversized topic into sub-segments at message boundaries."""
        segments: list[list[ChatMessage]] = []
        current: list[ChatMessage] = []
        current_chars = 0

        header_overhead = 80

        for msg in messages:
            msg_text = self._format_message(msg)
            msg_chars = len(msg_text)

            if current and current_chars + msg_chars + header_overhead > max_chars:
                segments.append(list(current))
                if overlap_chars > 0 and len(current) >= 1:
                    current = [current[-1]]
                    current_chars = len(self._format_message(current[0]))
                else:
                    current = []
                    current_chars = 0

            current.append(msg)
            current_chars += msg_chars + (0 if len(current) == 1 else 1)

        if current:
            segments.append(list(current))

        return segments

    @staticmethod
    def _format_message(msg: ChatMessage) -> str:
        """Format a single chat message into a text line."""
        ts_label = f"[{msg.date_str} {msg.time_str}]"
        if msg.quoted_speaker and msg.content_type == "reply":
            quote_preview = (msg.quoted_content or "")[:60]
            if len(msg.quoted_content or "") > 60:
                quote_preview += "..."
            return (
                f"{ts_label} {msg.speaker}: {msg.content} "
                f"(回复{msg.quoted_speaker}: {quote_preview})"
            )
        if msg.content_type == "attachment":
            return f"{ts_label} {msg.speaker}: {msg.content}"
        return f"{ts_label} {msg.speaker}: {msg.content}"

    @staticmethod
    def _format_messages(messages: list[ChatMessage]) -> str:
        """Format a list of messages into chunk text with topic header."""
        lines: list[str] = []
        if messages:
            first = messages[0]
            last = messages[-1]
            speakers = list(dict.fromkeys(msg.speaker for msg in messages))
            speakers_str = "、".join(speakers)
            topic_header = (
                f"【聊天记录：{speakers_str} - "
                f"{first.date_str} {first.time_str} ~ {last.date_str} {last.time_str} "
                f"({len(messages)}条消息)】"
            )
            lines.append(topic_header)
            lines.extend(
                ChatRecordChunkingStrategy._format_message(msg) for msg in messages
            )
        return "\n".join(lines)


class ChunkingStrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, ChunkingStrategy] = {
            "fixed": FixedChunkingStrategy(),
            "structural": StructuralChunkingStrategy(),
            "table-aware": TableAwareChunkingStrategy(),
            "parent-child": ParentChildChunkingStrategy(),
            "semantic": SemanticChunkingStrategy(),
            "chat-record": ChatRecordChunkingStrategy(),
        }

    def get(self, name: str) -> ChunkingStrategy:
        normalized = name.strip().lower()
        return self._strategies.get(normalized, self._strategies["fixed"])

    def list_strategies(self) -> list[dict]:
        return [
            {
                "name": strategy.name,
                "params_schema": strategy.params_schema,
            }
            for strategy in self._strategies.values()
        ]

    def register(self, name: str, strategy: ChunkingStrategy) -> None:
        self._strategies[name.strip().lower()] = strategy


def build_chunks(
    parsed_blocks: list[ParsedBlock],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    strategy: str = "fixed",
    table_rows_per_chunk: int = 20,
    options: ChunkingOptions | None = None,
    **extra_options,
) -> list[ChunkPayload]:
    chunk_options = options or ChunkingOptions(
        strategy=strategy,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        table_rows_per_chunk=table_rows_per_chunk,
    )

    if options is not None and getattr(chunk_options, "strategy", None):
        strategy = chunk_options.strategy

    for key, value in extra_options.items():
        if hasattr(chunk_options, key):
            setattr(chunk_options, key, value)

    return ChunkingStrategyRegistry().get(strategy).build_chunks(parsed_blocks, options=chunk_options)


def _build_chunk_payload(
    chunk_index: int,
    block: ParsedBlock,
    chunk_text: str,
    metadata: dict,
    row_start: int | None = None,
    row_end: int | None = None,
) -> ChunkPayload:
    return ChunkPayload(
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        chunk_type=block.chunk_type,
        section_title=block.section_title,
        page_no=block.page_no,
        sheet_name=block.sheet_name,
        row_start=block.row_start if row_start is None else row_start,
        row_end=block.row_end if row_end is None else row_end,
        token_count=estimate_token_count(chunk_text),
        char_count=len(chunk_text),
        metadata_json=metadata,
    )
