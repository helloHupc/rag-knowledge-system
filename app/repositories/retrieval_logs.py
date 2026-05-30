from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.retrieval_log import RetrievalLog


class RetrievalLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, log: RetrievalLog) -> RetrievalLog:
        self.session.add(log)
        self.session.flush()
        return log
