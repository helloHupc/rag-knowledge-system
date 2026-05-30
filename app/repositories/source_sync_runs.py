from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.source_sync_item import SourceSyncItem
from app.models.source_sync_run import SourceSyncRun


class SourceSyncRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_run(self, run: SourceSyncRun) -> SourceSyncRun:
        self.session.add(run)
        self.session.flush()
        return run

    def add_items(self, items: list[SourceSyncItem]) -> None:
        self.session.add_all(items)
        self.session.flush()

    def get_run_by_uuid(self, run_uuid: uuid.UUID) -> SourceSyncRun | None:
        stmt = select(SourceSyncRun).where(SourceSyncRun.run_uuid == run_uuid)
        return self.session.scalar(stmt)

    def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        source_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[SourceSyncRun], int]:
        stmt = select(SourceSyncRun)
        count_stmt = select(func.count()).select_from(SourceSyncRun)

        if source_type:
            stmt = stmt.where(SourceSyncRun.source_type == source_type)
            count_stmt = count_stmt.where(SourceSyncRun.source_type == source_type)
        if status:
            stmt = stmt.where(SourceSyncRun.status == status)
            count_stmt = count_stmt.where(SourceSyncRun.status == status)

        stmt = stmt.order_by(SourceSyncRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        runs = list(self.session.scalars(stmt))
        total = self.session.scalar(count_stmt) or 0
        return runs, total

    def list_items_by_run(self, run_uuid: uuid.UUID) -> list[SourceSyncItem]:
        stmt = select(SourceSyncItem).where(SourceSyncItem.run_uuid == run_uuid).order_by(SourceSyncItem.id.asc())
        return list(self.session.scalars(stmt))
