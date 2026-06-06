from __future__ import annotations

import logging
from typing import Iterable

from app.core.config import Settings
from app.db.runtime import get_session_factory
from app.integrations.feishu_client import FeishuClient
from app.integrations.wecom_client import WecomClient
from app.schemas.bot import BotReplyTarget
from app.schemas.qa import AnswerRequest, AnswerResponseData
from app.schemas.retrieval import RetrievalFilters, SearchRequest, SearchResponseData, UserContext
from app.services.qa import QaService
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


class BotDispatchService:
    def __init__(self, session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def answer_query(self, query: str, *, source_module: list[str] | None = None) -> str:
        query = query.strip()
        if not query:
            return "请发送需要查询的问题。"

        user_ctx = UserContext(user_id=f"bot:{self.settings.app_name}")
        filters = RetrievalFilters(source_module=source_module) if source_module else None

        if self.settings.bot_response_mode == "qa":
            result = QaService(self.session).answer(
                AnswerRequest(
                    question=query,
                    top_k=self.settings.bot_top_k,
                    filters=filters,
                    user_context=user_ctx,
                ),
                authenticated_identity_required=False,
            )
            return self._format_qa(result)

        result = RetrievalService(self.session).search(
            SearchRequest(
                query=query,
                top_k=self.settings.bot_top_k,
                filters=filters,
                user_context=user_ctx,
            ),
            authenticated_identity_required=False,
        )
        return self._format_search(result)

    def _format_qa(self, result: AnswerResponseData) -> str:
        parts = [result.answer.strip() or "未生成答案。"]
        source_text = self._format_sources(result.citations)
        if source_text:
            parts.append(source_text)
        return "\n\n".join(parts)

    def _format_search(self, result: SearchResponseData) -> str:
        if not result.hits:
            return "未找到相关知识片段。"
        lines = ["命中的知识片段："]
        for idx, hit in enumerate(result.hits, start=1):
            lines.append(f"{idx}. {hit.title}（score={hit.score:.3f}）：{hit.snippet}")
        source_text = self._format_sources(result.hits)
        if source_text:
            lines.append("")
            lines.append(source_text)
        return "\n".join(lines)

    @staticmethod
    def _format_sources(citations: Iterable) -> str:
        lines = []
        seen = set()
        for citation in citations:
            key = (citation.doc_uuid, citation.title)
            if key in seen:
                continue
            seen.add(key)
            location = citation.section_title or citation.sheet_name or (f"第 {citation.page_no} 页" if citation.page_no else "")
            suffix = f" - {location}" if location else ""
            lines.append(f"- {citation.title}{suffix}")
            if len(lines) >= 5:
                break
        if not lines:
            return ""
        return "来源：\n" + "\n".join(lines)


def run_bot_reply(platform: str, query: str, target: BotReplyTarget, settings: Settings, source_module: list[str] | None = None) -> None:
    session = get_session_factory()()
    try:
        answer = BotDispatchService(session, settings).answer_query(query, source_module=source_module)
        if platform == "feishu":
            FeishuClient(settings).reply(target, answer)
        elif platform == "wecom":
            WecomClient(settings).send(target, answer)
        else:
            logger.warning("Unsupported bot platform: %s", platform)
    except Exception:
        logger.exception("bot reply failed: platform=%s", platform)
    finally:
        session.close()
