from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.integrations.http_client import post_json_with_retries
from app.integrations.http_utils import build_openai_compatible_url
from app.schemas.qa import GenerationOptions
from app.schemas.retrieval import Citation


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LlmResult:
    answer: str
    provider_name: str
    model_name: str
    request_tokens: int
    response_tokens: int | None
    latency_ms: int


class LlmProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.llm_api_base and self.settings.llm_api_key and self.settings.llm_model)

    def probe(self) -> bool:
        if not self.is_configured():
            return False
        try:
            headers = {
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.settings.llm_model,
                "messages": [
                    {"role": "system", "content": "You are a health probe."},
                    {"role": "user", "content": "Reply with pong."},
                ],
                "temperature": 0,
                "max_tokens": 8,
                "stream": False,
            }
            request_url = build_openai_compatible_url(self.settings.llm_api_base, "/chat/completions")
            data = post_json_with_retries(
                settings=self.settings,
                url=request_url,
                headers=headers,
                payload=payload,
                timeout=min(15, max(5, self.settings.provider_timeout_seconds)),
                error_factory=lambda exc: AppError(
                    code=ErrorCode.LLM_GENERATION_FAILED,
                    message=f"llm provider probe failed: {exc}",
                    status_code=422,
                ),
            )
            choices = data.get("choices", [])
            if not choices:
                return False
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict)
                )
            return isinstance(content, str) and bool(content.strip())
        except AppError:
            return False

    def generate_answer(
        self,
        *,
        question: str,
        citations: list[Citation],
        generation_options: GenerationOptions | None,
    ) -> LlmResult:
        if not self.is_configured():
            raise AppError(
                code=ErrorCode.LLM_GENERATION_FAILED,
                message="llm provider is not configured",
                status_code=422,
            )

        system_prompt = (
            "你是企业知识库问答助手。只能基于给定引用回答，"
            "不要编造制度内容；如果证据不足，要明确说明未找到足够依据；"
            "并且优先使用用户提问所用的语言回答。"
        )
        citation_blocks = "\n\n".join(
            f"[{index}] 标题: {citation.title}\n"
            f"模块: {citation.source_module}\n"
            f"位置: {citation.section_title or citation.sheet_name or citation.page_no or 'chunk'}\n"
            f"内容: {citation.snippet}"
            for index, citation in enumerate(citations, start=1)
        )
        user_prompt = f"问题：{question}\n\n引用片段：\n{citation_blocks}\n\n请基于引用作答。"
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": generation_options.temperature if generation_options else self.settings.llm_temperature,
            "max_tokens": generation_options.max_tokens if generation_options else self.settings.llm_max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        request_url = build_openai_compatible_url(self.settings.llm_api_base, "/chat/completions")
        started = perf_counter()
        data = post_json_with_retries(
            settings=self.settings,
            url=request_url,
            headers=headers,
            payload=payload,
            timeout=max(60, self.settings.provider_timeout_seconds),
            error_factory=lambda exc: AppError(
                code=ErrorCode.LLM_GENERATION_FAILED,
                message=f"llm provider request failed: {exc}",
                status_code=422,
            ),
        )

        choices = data.get("choices", [])
        if not choices:
            raise AppError(
                code=ErrorCode.LLM_GENERATION_FAILED,
                message="llm provider returned no choices",
                status_code=422,
            )
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise AppError(
                code=ErrorCode.LLM_GENERATION_FAILED,
                message="llm provider returned empty content",
                status_code=422,
            )
        usage = data.get("usage", {})
        latency_ms = int((perf_counter() - started) * 1000)
        return LlmResult(
            answer=content.strip(),
            provider_name=self.settings.llm_api_base,
            model_name=data.get("model") or self.settings.llm_model,
            request_tokens=usage.get("prompt_tokens", len(user_prompt.split())),
            response_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )

    def generate_answer_with_fallback(
        self,
        *,
        question: str,
        citations: list[Citation],
        generation_options: GenerationOptions | None,
        fallback_builder,
    ) -> LlmResult | None:
        if not self.is_configured():
            return None
        try:
            return self.generate_answer(
                question=question,
                citations=citations,
                generation_options=generation_options,
            )
        except AppError:
            if not self.settings.allow_provider_fallbacks:
                raise
            logger.warning("LLM provider failed; falling back to local grounded answer builder")
            return LlmResult(
                answer=fallback_builder(citations),
                provider_name="local-fallback",
                model_name="local-grounded-answer",
                request_tokens=0,
                response_tokens=None,
                latency_ms=0,
            )
