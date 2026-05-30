from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.trace import get_trace_id
from app.integrations.llm import LlmProvider
from app.models.llm_call_log import LlmCallLog
from app.repositories.llm_call_logs import LlmCallLogRepository
from app.schemas.qa import AnswerRequest, AnswerResponseData, LatencyBreakdown, MatchedDocument
from app.schemas.retrieval import SearchRequest
from app.services.retrieval import RetrievalService


class QaService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.retrieval = RetrievalService(session)
        self.llm_provider = LlmProvider(self.settings)
        self.llm_logs = LlmCallLogRepository(session)

    def answer(
        self,
        request: AnswerRequest,
        *,
        trusted_user_context: bool = False,
        authenticated_identity_required: bool = False,
    ) -> AnswerResponseData:
        started = time.perf_counter()
        retrieval_started = time.perf_counter()
        retrieval_result = self.retrieval.search(
            SearchRequest(
                query=request.question,
                top_k=request.top_k,
                filters=request.filters,
                user_context=request.user_context,
            ),
            trusted_user_context=trusted_user_context,
            authenticated_identity_required=authenticated_identity_required,
        )
        retrieval_latency = int((time.perf_counter() - retrieval_started) * 1000)

        generation_started = time.perf_counter()
        answer_status = "grounded"
        if retrieval_result.hits and self._has_sufficient_evidence(retrieval_result.hits):
            if self.llm_provider.is_configured():
                llm_result = self.llm_provider.generate_answer_with_fallback(
                    question=request.question,
                    citations=retrieval_result.hits,
                    generation_options=request.generation_options,
                    fallback_builder=self._build_grounded_answer,
                )
                if llm_result is not None:
                    answer = llm_result.answer
                    self._record_llm_log(llm_result)
                else:
                    answer = self._build_grounded_answer(retrieval_result.hits)
            else:
                answer = self._build_grounded_answer(retrieval_result.hits)
        else:
            answer_status = "insufficient_evidence"
            answer = "未找到足够依据，请缩小范围或补充筛选条件后重试。"
        generation_latency = int((time.perf_counter() - generation_started) * 1000)
        total_latency = int((time.perf_counter() - started) * 1000)

        matched_documents = []
        seen_doc_ids = set()
        for citation in retrieval_result.hits:
            if citation.doc_uuid in seen_doc_ids:
                continue
            seen_doc_ids.add(citation.doc_uuid)
            matched_documents.append(
                MatchedDocument(
                    doc_uuid=citation.doc_uuid,
                    title=citation.title,
                    score=citation.score,
                )
            )

        return AnswerResponseData(
            answer=answer,
            answer_status=answer_status,
            citations=retrieval_result.hits,
            matched_documents=matched_documents,
            filters_applied=retrieval_result.filters_applied,
            latency_ms=LatencyBreakdown(
                retrieval=retrieval_latency,
                generation=generation_latency,
                total=total_latency,
            ),
        )

    @staticmethod
    def _build_grounded_answer(citations) -> str:
        snippets = []
        for citation in citations[:3]:
            location = citation.section_title or citation.sheet_name or (f"page {citation.page_no}" if citation.page_no else "chunk")
            snippets.append(f"- {citation.title}（{location}，score={citation.score:.3f}）：{citation.snippet}")
        return "基于命中的引用片段，当前可确认的信息如下：\n" + "\n".join(snippets)

    @staticmethod
    def _has_sufficient_evidence(citations) -> bool:
        if not citations:
            return False
        top = citations[0]
        if top.score < 0.35:
            return False
        # text_score 为 None 时跳过检查（纯向量检索模式）
        if top.text_score is not None and top.text_score < 0.2:
            return False
        return True

    def _record_llm_log(self, llm_result) -> None:
        status = "fallback" if llm_result.provider_name == "local-fallback" else "success"
        self.llm_logs.add(
            LlmCallLog(
                trace_id=get_trace_id(),
                provider_type="llm",
                provider_name=llm_result.provider_name,
                model_name=llm_result.model_name,
                request_type="chat.completions",
                request_tokens=llm_result.request_tokens,
                response_tokens=llm_result.response_tokens,
                latency_ms=llm_result.latency_ms,
                status=status,
            )
        )
        self.session.commit()
