from __future__ import annotations

from pathlib import Path
from typing import Iterator

from docx import Document as DocxDocument
from docx.document import Document as DocxRootDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.parsers.common import normalize_text
from app.ingestion.types import ParsedBlock


def iter_block_items(parent: DocxRootDocument) -> Iterator[Paragraph | Table]:
    parent_element = parent.element.body
    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


class DocxParser:
    def parse(self, file_path: Path) -> list[ParsedBlock]:
        document = DocxDocument(file_path)
        blocks: list[ParsedBlock] = []
        current_heading: str | None = None
        paragraph_buffer: list[str] = []

        def flush_paragraphs() -> None:
            nonlocal paragraph_buffer
            if not paragraph_buffer:
                return
            text = normalize_text("\n".join(paragraph_buffer))
            if text:
                blocks.append(
                    ParsedBlock(
                        text=text,
                        section_title=current_heading,
                        metadata={"parser": "python-docx"},
                    )
                )
            paragraph_buffer = []

        for item in iter_block_items(document):
            if isinstance(item, Paragraph):
                text = normalize_text(item.text)
                if not text:
                    continue
                style_name = item.style.name if item.style is not None else ""
                if style_name.lower().startswith("heading"):
                    flush_paragraphs()
                    current_heading = text
                    continue
                paragraph_buffer.append(text)
            else:
                flush_paragraphs()
                table_rows: list[str] = []
                for row in item.rows:
                    cells = [normalize_text(cell.text) for cell in row.cells]
                    cleaned = [cell for cell in cells if cell]
                    if cleaned:
                        table_rows.append(" | ".join(cleaned))
                table_text = normalize_text("\n".join(table_rows))
                if table_text:
                    blocks.append(
                        ParsedBlock(
                            text=table_text,
                            chunk_type="table",
                            section_title=current_heading,
                            metadata={"parser": "python-docx", "table": True},
                        )
                    )

        flush_paragraphs()
        return blocks
