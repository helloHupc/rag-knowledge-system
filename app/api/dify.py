from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id, verify_dify_bearer_token
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.responses import success_response
from app.schemas.dify import (
    DifyDocumentSummary,
    DifyExternalRecord,
    DifyExternalRetrievalRequest,
    DifyExternalRetrievalResponse,
    DifyKnowledgeRequest,
    DifyKnowledgeResponseData,
)
from app.schemas.qa import AnswerRequest
from app.schemas.retrieval import RetrievalFilters, SearchRequest, UserContext
from app.services.qa import QaService
from app.services.retrieval import RetrievalService


router = APIRouter(prefix="/dify", tags=["dify"])


def _resolve_dify_filters(request: DifyExternalRetrievalRequest) -> tuple[RetrievalFilters | None, list[str]]:
    source_module_values: list[str] = []
    source_type_values: list[str] = []
    file_ext_values: list[str] = []
    explicit_doc_uuids: list[str] = []
    knowledge_id = request.knowledge_id.strip()
    if knowledge_id:
        if knowledge_id.startswith("doc_uuid:"):
            explicit_doc_uuid = knowledge_id.removeprefix("doc_uuid:").strip()
            if explicit_doc_uuid:
                explicit_doc_uuids.append(explicit_doc_uuid)
        else:
            # 支持逗号分隔多个source_module，如 "oa,kf"
            source_module_values.extend([item.strip() for item in knowledge_id.split(",") if item.strip()])

    metadata = request.metadata_condition
    if metadata:
        for condition in metadata.conditions:
            name = condition.name.strip().lower()
            operator = condition.comparison_operator.strip().lower()
            if operator not in {"=", "==", "in"}:
                continue
            value = condition.value
            values = value if isinstance(value, list) else [value]
            normalized_values = [str(item).strip() for item in values if item is not None and str(item).strip()]
            if not normalized_values:
                continue
            if name == "source_module":
                source_module_values.extend(normalized_values)
            elif name == "source_type":
                source_type_values.extend(normalized_values)
            elif name == "file_ext":
                file_ext_values.extend(normalized_values)
            elif name == "doc_uuid":
                explicit_doc_uuids.extend(normalized_values)

    if not any([source_module_values, source_type_values, file_ext_values]):
        return None, explicit_doc_uuids

    return (
        RetrievalFilters(
            source_module=source_module_values or None,
            source_type=source_type_values or None,
            file_ext=file_ext_values or None,
        ),
        explicit_doc_uuids,
    )


def _build_dify_user_context(settings: Settings) -> UserContext:
    return UserContext(
        user_id=settings.dify_retrieval_user_id,
    )


def _build_dify_external_record(hit) -> DifyExternalRecord:
    return DifyExternalRecord(
        content=hit.snippet,
        score=hit.score,
        title=hit.title,
        metadata={
            "doc_uuid": hit.doc_uuid,
            "chunk_uuid": hit.chunk_uuid,
            "source_module": hit.source_module,
            "page_no": hit.page_no,
            "sheet_name": hit.sheet_name,
            "section_title": hit.section_title,
            "version": hit.version,
            "updated_at": hit.updated_at.isoformat(),
            "vector_score": hit.vector_score,
            "text_score": hit.text_score,
        },
    )


@router.post("/knowledge", response_model=dict)
def dify_knowledge(
    request: DifyKnowledgeRequest,
    trace_id: str = Depends(get_trace_id),
    _: str = Depends(verify_dify_bearer_token),
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
):
    service_user_context = _build_dify_user_context(settings)
    if request.response_mode == "search":
        retrieval_result = RetrievalService(session).search(
            SearchRequest(
                query=request.query,
                top_k=request.top_k,
                filters=request.filters,
                user_context=service_user_context,
            ),
        )
        documents: list[DifyDocumentSummary] = []
        seen: set[str] = set()
        for hit in retrieval_result.hits:
            if hit.doc_uuid in seen:
                continue
            seen.add(hit.doc_uuid)
            documents.append(
                DifyDocumentSummary(
                    doc_uuid=hit.doc_uuid,
                    title=hit.title,
                    source_module=hit.source_module,
                    score=hit.score,
                )
            )
        data = DifyKnowledgeResponseData(
            query=request.query,
            mode="search",
            answer="\n\n".join(
                f"[{index}] {hit.title}: {hit.snippet}"
                for index, hit in enumerate(retrieval_result.hits, start=1)
            ) or "未检索到可用知识片段。",
            answer_status="grounded" if retrieval_result.hits else "insufficient_evidence",
            references=retrieval_result.hits,
            documents=documents,
            filters_applied=retrieval_result.filters_applied,
            latency_ms={"retrieval": retrieval_result.latency_ms, "total": retrieval_result.latency_ms},
        )
        return success_response(data.model_dump(mode="json"), trace_id)

    qa_result = QaService(session).answer(
        AnswerRequest(
            question=request.query,
            top_k=request.top_k,
            filters=request.filters,
            user_context=service_user_context,
            generation_options=request.generation_options,
        )
    )
    data = DifyKnowledgeResponseData(
        query=request.query,
        mode="qa",
        answer=qa_result.answer,
        answer_status=qa_result.answer_status,
        references=qa_result.citations,
        documents=[
            DifyDocumentSummary(
                doc_uuid=item.doc_uuid,
                title=item.title,
                source_module=next(
                    (
                        citation.source_module
                        for citation in qa_result.citations
                        if citation.doc_uuid == item.doc_uuid
                    ),
                    "",
                ),
                score=item.score,
            )
            for item in qa_result.matched_documents
        ],
        filters_applied=qa_result.filters_applied,
        latency_ms=qa_result.latency_ms.model_dump(),
    )
    return success_response(data.model_dump(mode="json"), trace_id)


@router.post("/retrieval", response_model=DifyExternalRetrievalResponse)
def dify_external_retrieval(
    request: DifyExternalRetrievalRequest,
    _: str = Depends(verify_dify_bearer_token),
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
):
    filters, explicit_doc_uuids = _resolve_dify_filters(request)
    top_k = max(1, min(request.retrieval_setting.top_k, 20))
    min_score = max(0.0, min(request.retrieval_setting.score_threshold, 1.0))

    retrieval_result = RetrievalService(session).search(
        SearchRequest(
            query=request.query,
            top_k=top_k,
            min_score=min_score,
            filters=filters,
            user_context=_build_dify_user_context(settings),
        ),
    )

    if explicit_doc_uuids:
        normalized_doc_uuids: set[str] = set()
        for item in explicit_doc_uuids:
            try:
                normalized_doc_uuids.add(str(UUID(item)))
            except ValueError as exc:
                raise AppError(
                    code=ErrorCode.INVALID_REQUEST,
                    message=f"invalid doc_uuid in knowledge_id or metadata_condition: {item}",
                    status_code=422,
                ) from exc
        hits = [hit for hit in retrieval_result.hits if hit.doc_uuid in normalized_doc_uuids]
    else:
        hits = retrieval_result.hits

    payload = DifyExternalRetrievalResponse(records=[_build_dify_external_record(hit) for hit in hits])
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))
