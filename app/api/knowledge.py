from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep, get_trace_id
from app.core.config import Settings
from app.core.responses import success_response
from app.schemas.knowledge import (
    KnowledgeQueryReference,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
)
from app.schemas.retrieval import SearchRequest, UserContext
from app.schemas.qa import AnswerRequest
from app.services.retrieval import RetrievalService
from app.services.qa import QaService


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _build_default_user_context() -> UserContext:
    return UserContext(user_id="knowledge-api")


def _citation_to_reference(citation) -> KnowledgeQueryReference:
    return KnowledgeQueryReference(
        doc_uuid=citation.doc_uuid,
        chunk_uuid=citation.chunk_uuid,
        title=citation.title,
        source_module=citation.source_module,
        snippet=citation.snippet,
        score=citation.score,
        page_no=citation.page_no,
        sheet_name=citation.sheet_name,
        section_title=citation.section_title,
        version=citation.version,
        updated_at=citation.updated_at.isoformat() if citation.updated_at else None,
        vector_score=citation.vector_score,
        text_score=citation.text_score,
    )


@router.post("/query", response_model=dict)
def knowledge_query(
    request: KnowledgeQueryRequest,
    trace_id: str = Depends(get_trace_id),
    settings: Settings = Depends(get_settings_dep),
    session: Session = Depends(get_session),
):
    """通用知识库查询接口

    支持 search（纯检索）和 qa（检索+问答）两种模式。
    可通过 filters.source_module 按知识库筛选。
    """
    user_context = _build_default_user_context()

    if request.response_mode == "qa":
        qa_result = QaService(session).answer(
            AnswerRequest(
                question=request.query,
                top_k=request.top_k,
                filters=request.filters,
                user_context=user_context,
                generation_options=request.generation_options,
            ),
            authenticated_identity_required=False,
        )
        references = [_citation_to_reference(c) for c in qa_result.citations]
        data = KnowledgeQueryResponse(
            query=request.query,
            mode="qa",
            answer=qa_result.answer,
            answer_status=qa_result.answer_status,
            references=references,
            filters_applied=qa_result.filters_applied,
            latency_ms=qa_result.latency_ms.model_dump(),
        )
        return success_response(data.model_dump(mode="json"), trace_id)

    retrieval_result = RetrievalService(session).search(
        SearchRequest(
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            filters=request.filters,
            user_context=user_context,
        ),
        authenticated_identity_required=False,
    )
    references = [_citation_to_reference(h) for h in retrieval_result.hits]
    answer_lines = [
        f"[{i}] {h.title}: {h.snippet}"
        for i, h in enumerate(retrieval_result.hits, start=1)
    ]
    data = KnowledgeQueryResponse(
        query=request.query,
        mode="search",
        answer="\n\n".join(answer_lines) or "未检索到可用知识片段。",
        answer_status="grounded" if retrieval_result.hits else "insufficient_evidence",
        references=references,
        filters_applied=retrieval_result.filters_applied,
        latency_ms={"retrieval": retrieval_result.latency_ms, "total": retrieval_result.latency_ms},
    )
    return success_response(data.model_dump(mode="json"), trace_id)
