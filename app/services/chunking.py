from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.ingestion.parser_registry import ParserRegistry
from app.ingestion.chunking import (
    ChunkingStrategyRegistry,
    build_chunks,
)
from app.ingestion.types import ChunkingOptions, ParsedBlock
from app.repositories.documents import DocumentRepository


class ChunkingService:
    def __init__(self, session: Session | None = None) -> None:
        self._registry = ChunkingStrategyRegistry()
        self._parser_registry = ParserRegistry()
        self._documents = DocumentRepository(session) if session is not None else None

    def list_strategies(self) -> list[dict]:
        return self._registry.list_strategies()

    def preview(
        self,
        *,
        strategy: str,
        text: str,
        options: dict | None = None,
    ) -> dict:
        parsed_blocks = [
            ParsedBlock(
                text=text,
                chunk_type="text",
            )
        ]
        chunk_payloads = build_chunks(parsed_blocks, options=self._build_chunk_options(strategy=strategy, options=options))
        return self._serialize_preview_result(strategy=strategy, chunk_payloads=chunk_payloads)

    def preview_document(
        self,
        *,
        doc_uuid,
        strategy: str,
        options: dict | None = None,
    ) -> dict:
        parsed_blocks = self._parse_document_blocks(doc_uuid)
        chunk_payloads = build_chunks(parsed_blocks, options=self._build_chunk_options(strategy=strategy, options=options))
        return self._serialize_preview_result(strategy=strategy, chunk_payloads=chunk_payloads)

    def get_document_preview_text(
        self,
        *,
        doc_uuid,
        max_chars: int = 12000,
    ) -> dict:
        if self._documents is None:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="session is required for document preview",
                status_code=400,
            )

        document, parsed_blocks = self._load_document_and_blocks(doc_uuid)

        text = "\n\n".join(block.text.strip() for block in parsed_blocks if block.text and block.text.strip()).strip()
        truncated = len(text) > max_chars
        preview_text = text[:max_chars].strip() if truncated else text

        return {
            "doc_uuid": str(document.doc_uuid),
            "title": document.title,
            "text": preview_text,
            "char_count": len(text),
            "truncated": truncated,
            "block_count": len(parsed_blocks),
        }

    def _build_chunk_options(self, *, strategy: str, options: dict | None = None) -> ChunkingOptions:
        opts = options or {}
        return ChunkingOptions(
            strategy=strategy,
            max_chars=opts.get("max_chars", 1200),
            overlap_chars=opts.get("overlap_chars", 150),
            table_rows_per_chunk=opts.get("table_rows_per_chunk", 20),
            parent_max_chars=opts.get("parent_max_chars", 3000),
            child_max_chars=opts.get("child_max_chars", 600),
            min_chunk_sentences=opts.get("min_chunk_sentences", 3),
            max_chunk_sentences=opts.get("max_chunk_sentences", 20),
            similarity_threshold=opts.get("similarity_threshold", 0.5),
            merge_window=opts.get("merge_window", 3),
        )

    def _serialize_preview_result(self, *, strategy: str, chunk_payloads: list) -> dict:
        return {
            "strategy": strategy,
            "total_chunks": len(chunk_payloads),
            "chunks": [
                {
                    "chunk_index": p.chunk_index,
                    "chunk_text": p.chunk_text,
                    "chunk_type": p.chunk_type,
                    "section_title": p.section_title,
                    "page_no": p.page_no,
                    "sheet_name": p.sheet_name,
                    "row_start": p.row_start,
                    "row_end": p.row_end,
                    "char_count": p.char_count,
                    "token_count": p.token_count,
                    "chunk_level": p.chunk_level,
                    "parent_chunk_uuid": p.parent_chunk_uuid,
                    "chunk_group_uuid": p.chunk_group_uuid,
                    "context_text": p.context_text,
                    "metadata_json": p.metadata_json,
                }
                for p in chunk_payloads
            ],
        }

    def _parse_document_blocks(self, doc_uuid):
        _, parsed_blocks = self._load_document_and_blocks(doc_uuid)
        return parsed_blocks

    def _load_document_and_blocks(self, doc_uuid):
        if self._documents is None:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message="session is required for document preview",
                status_code=400,
            )

        document = self._documents.get_by_uuid(doc_uuid)
        if document is None:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document not found",
                status_code=404,
            )

        file_path = Path(document.file_path)
        if not file_path.exists():
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="document file not found",
                status_code=404,
            )

        parsed_blocks = self._parser_registry.parse(document.file_ext, file_path)
        if not parsed_blocks:
            raise AppError(
                code=ErrorCode.DOCUMENT_PARSE_FAILED,
                message="document parser produced no text blocks",
                status_code=422,
            )

        return document, parsed_blocks
