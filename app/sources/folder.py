from __future__ import annotations

import mimetypes
from pathlib import Path

from app.core.errors import AppError, ErrorCode
from app.sources.types import SourceDocument, SourceReadResult


class FolderSourceConnector:
    name = "folder"

    def __init__(
        self,
        folder_path: Path,
        *,
        recursive: bool = True,
        allowed_extensions: set[str] | None = None,
        max_files: int = 100,
    ) -> None:
        self.folder_path = folder_path.expanduser().resolve()
        self.recursive = recursive
        self.allowed_extensions = {item.lower().lstrip(".") for item in allowed_extensions or set()}
        self.max_files = max_files

    async def read(self) -> SourceReadResult:
        if not self.folder_path.exists() or not self.folder_path.is_dir():
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="folder path does not exist or is not a directory",
            )

        if self.max_files <= 0:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="max_files must be greater than 0",
            )

        documents: list[SourceDocument] = []
        skipped: list[dict] = []
        for file_path in self._iter_files():
            relative_path = str(file_path.relative_to(self.folder_path))
            extension = file_path.suffix.lower().lstrip(".")
            if self.allowed_extensions and extension not in self.allowed_extensions:
                skipped.append(
                    {
                        "file_name": file_path.name,
                        "relative_path": relative_path,
                        "reason": "unsupported_extension",
                    }
                )
                continue

            try:
                stat = file_path.stat()
                content = file_path.read_bytes()
            except OSError as exc:
                skipped.append(
                    {
                        "file_name": file_path.name,
                        "relative_path": relative_path,
                        "reason": "read_failed",
                        "message": str(exc),
                    }
                )
                continue

            documents.append(
                SourceDocument(
                    file_name=file_path.name,
                    content=content,
                    mime_type=mimetypes.guess_type(file_path.name)[0],
                    metadata={
                        "source_connector": self.name,
                        "source_path": str(file_path),
                        "relative_path": relative_path,
                        "source_mtime": stat.st_mtime,
                        "source_size": stat.st_size,
                    },
                )
            )
            if len(documents) >= self.max_files:
                break

        return SourceReadResult(
            source_name=self.name,
            documents=documents,
            metadata={
                "folder_path": str(self.folder_path),
                "recursive": self.recursive,
                "max_files": self.max_files,
                "skipped": skipped,
            },
        )

    def _iter_files(self):
        pattern = "**/*" if self.recursive else "*"
        for path in sorted(self.folder_path.glob(pattern)):
            if path.is_file():
                yield path
