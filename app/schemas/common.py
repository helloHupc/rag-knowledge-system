from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class AppBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApiResponse(AppBaseModel, Generic[T]):
    code: int
    message: str
    data: T | None
    trace_id: str


class ErrorDetail(AppBaseModel):
    code: int
    message: str
    data: Any | None = None
    trace_id: str
