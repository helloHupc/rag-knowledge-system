from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.ingestion.types import ParsedBlock


class DocumentParser(Protocol):
    def parse(self, file_path: Path) -> list[ParsedBlock]:
        ...
