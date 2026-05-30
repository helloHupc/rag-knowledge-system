from __future__ import annotations

from sqlalchemy import Index, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JsonType, PrimaryKeyBigInt
from app.models.mixins import TimestampMixin


class SystemConfig(TimestampMixin, Base):
    __tablename__ = "system_configs"
    __table_args__ = (Index("uq_system_configs_config_key", "config_key", unique=True),)

    id: Mapped[int] = mapped_column(PrimaryKeyBigInt, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    config_value: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict, server_default="{}")
    description: Mapped[str | None] = mapped_column(Text)
