from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.llm_call_log import LlmCallLog


class LlmCallLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, log: LlmCallLog) -> LlmCallLog:
        self.session.add(log)
        self.session.flush()
        return log
