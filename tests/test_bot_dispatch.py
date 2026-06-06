from __future__ import annotations

from datetime import datetime, UTC

from app.schemas.qa import AnswerResponseData, LatencyBreakdown, MatchedDocument
from app.schemas.retrieval import Citation, SearchResponseData
from app.services.bot_dispatch import BotDispatchService


def _citation() -> Citation:
    return Citation(
        doc_uuid="doc-1",
        chunk_uuid="chunk-1",
        title="调岗制度",
        source_module="oa",
        snippet="调岗申请需要二级审批。",
        version="v1",
        updated_at=datetime.now(UTC),
        score=0.91,
    )


def test_bot_dispatch_formats_qa_answer(db_session, monkeypatch):
    from app.core.config import get_settings, reset_settings_cache
    import app.services.bot_dispatch as module

    monkeypatch.setenv("BOT_RESPONSE_MODE", "qa")
    reset_settings_cache()

    class FakeQaService:
        def __init__(self, session):
            self.session = session

        def answer(self, request, *, authenticated_identity_required=False):
            assert request.question == "调岗怎么审批？"
            assert request.top_k == 8
            assert authenticated_identity_required is False
            return AnswerResponseData(
                answer="需要二级审批。",
                answer_status="grounded",
                citations=[_citation()],
                matched_documents=[MatchedDocument(doc_uuid="doc-1", title="调岗制度", score=0.91)],
                filters_applied={},
                latency_ms=LatencyBreakdown(retrieval=1, generation=1, total=2),
            )

    monkeypatch.setattr(module, "QaService", FakeQaService)
    answer = BotDispatchService(db_session, get_settings()).answer_query("调岗怎么审批？")

    assert "需要二级审批" in answer
    assert "来源" in answer
    assert "调岗制度" in answer


def test_bot_dispatch_formats_search_answer(db_session, monkeypatch):
    from app.core.config import get_settings, reset_settings_cache
    import app.services.bot_dispatch as module

    monkeypatch.setenv("BOT_RESPONSE_MODE", "search")
    monkeypatch.setenv("BOT_TOP_K", "3")
    reset_settings_cache()

    class FakeRetrievalService:
        def __init__(self, session):
            self.session = session

        def search(self, request, *, authenticated_identity_required=False):
            assert request.query == "调岗怎么审批？"
            assert request.top_k == 3
            assert authenticated_identity_required is False
            return SearchResponseData(
                query=request.query,
                rewritten_query=request.query,
                filters_applied={},
                hits=[_citation()],
                latency_ms=1,
            )

    monkeypatch.setattr(module, "RetrievalService", FakeRetrievalService)
    answer = BotDispatchService(db_session, get_settings()).answer_query("调岗怎么审批？")

    assert "命中的知识片段" in answer
    assert "调岗申请需要二级审批" in answer
    assert "来源" in answer
