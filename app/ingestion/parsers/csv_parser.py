from __future__ import annotations

import csv
from pathlib import Path

from app.ingestion.types import ParsedBlock


class CsvParser:
    def __init__(self, rows_per_block: int = 50) -> None:
        self.rows_per_block = rows_per_block

    def parse(self, file_path: Path) -> list[ParsedBlock]:
        rows = self._read_rows(file_path)
        if not rows:
            return []

        headers = rows[0]
        data_rows = rows[1:] or rows
        blocks: list[ParsedBlock] = []
        current_start = 2 if len(rows) > 1 else 1

        for index in range(0, len(data_rows), self.rows_per_block):
            batch = data_rows[index : index + self.rows_per_block]
            row_start = current_start + index
            row_end = row_start + len(batch) - 1
            lines = [" | ".join(headers)]
            for row in batch:
                entries = []
                for cell_index, value in enumerate(row):
                    header = headers[cell_index] if cell_index < len(headers) and headers[cell_index] else f"column_{cell_index + 1}"
                    if value:
                        entries.append(f"{header}: {value}")
                if entries:
                    lines.append("; ".join(entries))
            if lines:
                blocks.append(
                    ParsedBlock(
                        text="\n".join(lines),
                        chunk_type="table",
                        row_start=row_start,
                        row_end=row_end,
                        metadata={"parser": "csv", "headers": headers},
                    )
                )

        return blocks

    @staticmethod
    def _read_rows(file_path: Path) -> list[list[str]]:
        raw_text = file_path.read_text(encoding="utf-8-sig", errors="ignore")
        reader = csv.reader(raw_text.splitlines())
        return [
            [cell.strip() for cell in row]
            for row in reader
            if any(cell.strip() for cell in row)
        ]
