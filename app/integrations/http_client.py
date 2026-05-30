from __future__ import annotations

from collections.abc import Callable
from time import sleep

import httpx

from app.core.config import Settings
from app.core.errors import AppError


def post_json_with_retries(
    *,
    settings: Settings,
    url: str,
    headers: dict,
    payload: dict,
    timeout: float | None = None,
    error_factory: Callable[[Exception], AppError],
) -> dict:
    retries = settings.provider_retry_count + 1
    last_error: Exception | None = None
    request_timeout = timeout or settings.provider_timeout_seconds

    for attempt in range(retries):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=request_timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # pragma: no cover - exercised via caller tests
            last_error = exc
            if attempt >= retries - 1:
                break
            sleep(min(0.2 * (attempt + 1), 1.0))

    assert last_error is not None
    raise error_factory(last_error)
