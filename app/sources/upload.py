from __future__ import annotations

from fastapi import UploadFile

from app.core.errors import AppError, ErrorCode
from app.sources.types import SourceDocument, SourceReadResult


class UploadSourceConnector:
    name = "upload"

    def __init__(self, file: UploadFile) -> None:
        self.file = file

    async def read(self) -> SourceReadResult:
        if not self.file.filename:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="file name is required",
            )

        content = await self.file.read()
        return SourceReadResult(
            source_name=self.name,
            documents=[
                SourceDocument(
                    file_name=self.file.filename,
                    content=content,
                    mime_type=self.file.content_type,
                    metadata={"source_connector": self.name},
                )
            ],
        )
