from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_trace_id
from app.core.responses import success_response
from app.schemas.chunking import (
    ChunkingDocumentPreviewRequest,
    ChunkingPreviewRequest,
)
from app.services.chunking import ChunkingService


router = APIRouter(prefix="/chunking", tags=["chunking"])


@router.get("/strategies")
def get_strategies(trace_id: str = Depends(get_trace_id)) -> dict:
    service = ChunkingService()
    strategies = service.list_strategies()
    return success_response({"strategies": strategies}, trace_id)


@router.post("/preview")
def preview_chunking(request: ChunkingPreviewRequest, trace_id: str = Depends(get_trace_id)) -> dict:
    service = ChunkingService()
    result = service.preview(
        strategy=request.strategy,
        text=request.text,
        options=request.options,
    )
    return success_response(result, trace_id)


@router.post("/documents/{doc_uuid}/preview")
def preview_document_chunking(
    doc_uuid: UUID,
    request: ChunkingDocumentPreviewRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
) -> dict:
    service = ChunkingService(session)
    result = service.preview_document(
        doc_uuid=doc_uuid,
        strategy=request.strategy,
        options=request.options,
    )
    return success_response(result, trace_id)


@router.get("/documents/{doc_uuid}/preview-text")
def get_document_preview_text(
    doc_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
) -> dict:
    service = ChunkingService(session)
    result = service.get_document_preview_text(doc_uuid=doc_uuid)
    return success_response(result, trace_id)
