from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.system_config import SystemConfig


class SystemConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_configs(self, *, page: int, page_size: int, keyword: str | None = None) -> tuple[list[SystemConfig], int]:
        stmt = select(SystemConfig)
        count_stmt = select(func.count()).select_from(SystemConfig)
        if keyword:
            criterion = SystemConfig.config_key.ilike(f"%{keyword}%")
            stmt = stmt.where(criterion)
            count_stmt = count_stmt.where(criterion)
        stmt = stmt.order_by(SystemConfig.config_key.asc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.session.scalars(stmt))
        total = self.session.scalar(count_stmt) or 0
        return items, total

    def get_by_id(self, config_id: int) -> SystemConfig | None:
        return self.session.get(SystemConfig, config_id)

    def get_by_key(self, config_key: str) -> SystemConfig | None:
        stmt = select(SystemConfig).where(SystemConfig.config_key == config_key)
        return self.session.scalar(stmt)

    def add(self, config: SystemConfig) -> SystemConfig:
        self.session.add(config)
        self.session.flush()
        return config
