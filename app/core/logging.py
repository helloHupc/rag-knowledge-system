from __future__ import annotations

import logging
from logging.config import dictConfig

from app.core.trace import get_trace_id


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


def configure_logging(log_level: str) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"trace_id": {"()": TraceIdFilter}},
            "formatters": {
                "standard": {
                    "format": (
                        "%(asctime)s %(levelname)s "
                        "[trace_id=%(trace_id)s] %(name)s: %(message)s"
                    )
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "filters": ["trace_id"],
                }
            },
            "root": {"level": log_level.upper(), "handlers": ["default"]},
        }
    )
