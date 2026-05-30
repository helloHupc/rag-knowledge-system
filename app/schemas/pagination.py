from __future__ import annotations

from typing import Generic, TypeVar

from app.schemas.common import AppBaseModel


T = TypeVar("T")


class PaginatedResponse(AppBaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
