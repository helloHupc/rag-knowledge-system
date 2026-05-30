from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4


trace_id_context: ContextVar[str] = ContextVar("trace_id", default="-")


def generate_trace_id() -> str:
    return f"trc_{uuid4().hex}"


def get_trace_id() -> str:
    return trace_id_context.get()


def set_trace_id(trace_id: str) -> None:
    trace_id_context.set(trace_id)
