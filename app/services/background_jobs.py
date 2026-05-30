from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import UUID

from app.core.config import Settings
from app.db.runtime import get_session_factory
from app.services.ingestion import IngestionService


logger = logging.getLogger(__name__)


class BackgroundJobRunner:
    _executor: ThreadPoolExecutor | None = None
    _lock = Lock()

    @classmethod
    def submit_ingest_job(cls, *, doc_uuid: UUID, job_uuid: UUID, settings: Settings) -> None:
        executor = cls._get_executor()
        executor.submit(cls._run_ingest_job, doc_uuid, job_uuid, settings)

    @classmethod
    def shutdown(cls) -> None:
        with cls._lock:
            if cls._executor is not None:
                cls._executor.shutdown(wait=True, cancel_futures=False)
                cls._executor = None

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        with cls._lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oa-rag-bg")
            return cls._executor

    @staticmethod
    def _run_ingest_job(doc_uuid: UUID, job_uuid: UUID, settings: Settings) -> None:
        session = get_session_factory()()
        try:
            IngestionService(session, settings).resume_job(doc_uuid=doc_uuid, job_uuid=job_uuid)
            logger.info("Completed background ingestion job %s for document %s", job_uuid, doc_uuid)
        except Exception:
            logger.exception("Background ingestion job %s failed", job_uuid)
        finally:
            session.close()
