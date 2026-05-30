from __future__ import annotations

from typing import Any


def success_response(data: Any, trace_id: str) -> dict[str, Any]:
    return {
        "code": 0,
        "message": "ok",
        "data": data,
        "trace_id": trace_id,
    }


def error_response(
    *,
    code: int,
    message: str,
    trace_id: str,
    data: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "trace_id": trace_id,
    }
