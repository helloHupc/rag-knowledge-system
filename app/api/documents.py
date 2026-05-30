from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id
from app.core.config import Settings
from app.core.responses import success_response
from app.schemas.documents import (
    BatchDocumentOperationRequest,
    DocumentReindexResponse,
    DocumentUpdateRequest,
    DocumentUploadResponse,
)
from app.services.document_management import DocumentManagementService
from app.services.documents import DocumentService
from app.services.background_jobs import BackgroundJobRunner
from app.services.ingestion import IngestionService


router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=dict)
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_type: str | None = Query(default=None),
    source_module: str | None = Query(default=None),
    parse_status: str | None = Query(default=None),
    index_status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = DocumentManagementService(session).list_documents(
        page=page,
        page_size=page_size,
        source_type=source_type,
        source_module=source_module,
        parse_status=parse_status,
        index_status=index_status,
        keyword=keyword,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/{doc_uuid}", response_model=dict)
def get_document_detail(
    doc_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = DocumentManagementService(session).get_document_detail(doc_uuid)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.patch("/{doc_uuid}", response_model=dict)
def update_document(
    doc_uuid: UUID,
    request: DocumentUpdateRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = DocumentManagementService(session).update_document(doc_uuid, request)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/batch/reindex", response_model=dict)
def batch_reindex_documents(
    request: BatchDocumentOperationRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = DocumentManagementService(session).batch_reindex_documents(request.doc_uuids)
    return success_response(data.model_dump(mode="json"), trace_id)


@router.get("/{doc_uuid}/download")
def download_document(
    doc_uuid: UUID,
    session: Session = Depends(get_session),
):
    data = DocumentManagementService(session).get_document_detail(doc_uuid)
    if not data.file_path or not data.file_exists:
        from app.core.errors import AppError, ErrorCode

        raise AppError(
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="document file not found",
            status_code=404,
        )
    
    # 根据文件扩展名确定MIME类型
    import mimetypes
    mime_type, _ = mimetypes.guess_type(data.file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    
    # 图片文件使用inline显示，其他文件下载
    is_image = mime_type.startswith("image/")
    
    return FileResponse(
        path=data.file_path,
        filename=data.file_name,
        media_type=mime_type,
        content_disposition_type="inline" if is_image else "attachment",
    )


@router.post("/upload", response_model=dict)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_type: str = Form(...),
    source_module: str = Form(...),
    version: str = Form(default="v1"),
    access_level: str = Form(default="internal"),
    owner_dept: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    extra_meta: str | None = Form(default=None),
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    document, job, chunk_count = await DocumentService(settings, session).upload_document(
        file=file,
        title=title,
        source_type=source_type,
        source_module=source_module,
        version=version,
        access_level=access_level,
        owner_dept=owner_dept,
        tags=tags,
        extra_meta=extra_meta,
    )
    data = DocumentUploadResponse(
        doc_uuid=document.doc_uuid,
        job_uuid=job.job_uuid,
        status=job.status,
        chunk_count=chunk_count,
        execution_mode=settings.ingestion_mode,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/{doc_uuid}/reindex", response_model=dict)
def reindex_document(
    doc_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    if settings.ingestion_mode == "async":
        service = DocumentManagementService(session)
        document = service.require_document(doc_uuid)
        job = service.create_reindex_job(doc_uuid)
        BackgroundJobRunner.submit_ingest_job(
            doc_uuid=document.doc_uuid,
            job_uuid=job.job_uuid,
            settings=settings,
        )
        chunk_count = 0
    else:
        document, job, chunk_count = IngestionService(session, settings).reprocess_document(doc_uuid)
    data = DocumentReindexResponse(
        doc_uuid=document.doc_uuid,
        job_uuid=job.job_uuid,
        status=job.status,
        chunk_count=chunk_count,
        execution_mode=settings.ingestion_mode,
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.delete("/{doc_uuid}", response_model=dict)
def delete_document(
    doc_uuid: UUID,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    DocumentManagementService(session).delete_document(doc_uuid)
    return success_response({"doc_uuid": str(doc_uuid), "deleted": True}, trace_id)


@router.post("/batch/delete", response_model=dict)
def batch_delete_documents(
    request: BatchDocumentOperationRequest,
    trace_id: str = Depends(get_trace_id),
    session: Session = Depends(get_session),
):
    data = DocumentManagementService(session).batch_delete_documents(request.doc_uuids)
    return success_response(data.model_dump(mode="json"), trace_id)
