"""Evaluation service with isolated chunk storage and temporary vector collections.

Key guarantees:
- Writes chunks to evaluation_chunks (never touches document_chunks)
- Temporary vector collection: eval_<run_uuid>
- Serial queue via optimistic locking (status check)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.embedding import EmbeddingProvider
from app.integrations.vector_store import VectorStoreClient
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.evaluation_chunk import EvaluationChunk
from app.models.evaluation_dataset import EvaluationDataset
from app.models.evaluation_query import EvaluationQuery
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_run import EvaluationRun
from app.schemas.evaluation import (
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetResponse,
    QueryResponse,
    RunCreateRequest,
    RunDetailResponse,
    RunListResponse,
    RunResponse,
    RunResultResponse,
    RunSummary,
)
from app.schemas.retrieval import SearchRequest, UserContext
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


class EvaluationService:
    """Handles dataset CRUD and evaluation run lifecycle."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.embedding_provider = EmbeddingProvider(self.settings)
        self.vector_store = VectorStoreClient(self.settings)

    # ── Dataset CRUD ─────────────────────────────────────────────

    def create_dataset(self, req: DatasetCreateRequest) -> DatasetResponse:
        dataset = EvaluationDataset(
            dataset_uuid=uuid4(),
            name=req.name,
            description=req.description,
        )
        self.session.add(dataset)
        self.session.flush()

        for q in req.queries:
            eq = EvaluationQuery(
                query_uuid=uuid4(),
                dataset_uuid=dataset.dataset_uuid,
                query_text=q.query_text,
                expected_doc_titles=q.expected_doc_titles,
                expected_terms=q.expected_terms,
                notes=q.notes,
            )
            self.session.add(eq)

        self.session.commit()
        count = self._count_queries(dataset.dataset_uuid)
        return DatasetResponse(
            dataset_uuid=str(dataset.dataset_uuid),
            name=dataset.name,
            description=dataset.description,
            query_count=count,
            created_at=dataset.created_at,
        )

    def list_datasets(self) -> DatasetListResponse:
        stmt = select(EvaluationDataset).order_by(EvaluationDataset.created_at.desc())
        datasets = list(self.session.scalars(stmt))
        items = []
        for d in datasets:
            count = self._count_queries(d.dataset_uuid)
            items.append(DatasetResponse(
                dataset_uuid=str(d.dataset_uuid),
                name=d.name,
                description=d.description,
                query_count=count,
                created_at=d.created_at,
            ))
        return DatasetListResponse(datasets=items)

    def get_dataset(self, dataset_uuid: str) -> DatasetDetailResponse:
        ds = self._get_dataset(dataset_uuid)
        queries = self._get_queries(ds.dataset_uuid)
        return DatasetDetailResponse(
            dataset_uuid=str(ds.dataset_uuid),
            name=ds.name,
            description=ds.description,
            query_count=len(queries),
            created_at=ds.created_at,
            queries=[
                QueryResponse(
                    query_uuid=str(q.query_uuid),
                    query_text=q.query_text,
                    expected_doc_titles=q.expected_doc_titles,
                    expected_terms=q.expected_terms,
                    notes=q.notes,
                )
                for q in queries
            ],
        )

    def delete_dataset(self, dataset_uuid: str) -> None:
        ds = self._get_dataset(dataset_uuid)
        self.session.delete(ds)
        self.session.commit()

    # ── Run CRUD ──────────────────────────────────────────────────

    def create_run(self, req: RunCreateRequest) -> RunResponse:
        ds = self._get_dataset(req.dataset_uuid)
        run = EvaluationRun(
            run_uuid=uuid4(),
            dataset_uuid=ds.dataset_uuid,
            chunking_strategy=req.chunking_strategy,
            chunking_params=req.chunking_params or {},
            retrieval_strategy=req.retrieval_strategy,
            retrieval_params=req.retrieval_params or {},
            status="pending",
        )
        self.session.add(run)
        self.session.commit()

        # Execute asynchronously (in-process for now)
        self._execute_run(run, req.doc_uuids)

        return RunResponse(
            run_uuid=str(run.run_uuid),
            dataset_uuid=str(run.dataset_uuid),
            chunking_strategy=run.chunking_strategy,
            chunking_params=run.chunking_params,
            retrieval_strategy=run.retrieval_strategy,
            retrieval_params=run.retrieval_params,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
        )

    def list_runs(self, dataset_uuid: str | None = None) -> RunListResponse:
        stmt = select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
        if dataset_uuid:
            stmt = stmt.where(EvaluationRun.dataset_uuid == UUID(dataset_uuid))
        runs = list(self.session.scalars(stmt))
        
        # 获取所有相关的评测集名称
        dataset_uuids = list(set(r.dataset_uuid for r in runs))
        datasets = {}
        if dataset_uuids:
            ds_stmt = select(EvaluationDataset).where(EvaluationDataset.dataset_uuid.in_(dataset_uuids))
            for ds in self.session.scalars(ds_stmt):
                datasets[str(ds.dataset_uuid)] = ds.name
        
        return RunListResponse(
            runs=[
                RunResponse(
                    run_uuid=str(r.run_uuid),
                    dataset_uuid=str(r.dataset_uuid),
                    dataset_name=datasets.get(str(r.dataset_uuid)),
                    chunking_strategy=r.chunking_strategy,
                    chunking_params=r.chunking_params,
                    retrieval_strategy=r.retrieval_strategy,
                    retrieval_params=r.retrieval_params,
                    status=r.status,
                    started_at=r.started_at,
                    finished_at=r.finished_at,
                    created_at=r.created_at,
                )
                for r in runs
            ]
        )

    def get_run(self, run_uuid: str) -> RunDetailResponse:
        run = self._get_run(run_uuid)
        results = self._get_results(run.run_uuid)
        queries = {str(q.query_uuid): q for q in self._get_queries(run.dataset_uuid)}

        result_items = []
        for r in results:
            q = queries.get(str(r.query_uuid))
            result_items.append(RunResultResponse(
                query_uuid=str(r.query_uuid),
                query_text=q.query_text if q else "",
                hit_at_1=r.hit_at_1,
                hit_at_3=r.hit_at_3,
                hit_at_5=r.hit_at_5,
                mrr=r.mrr,
                expected_term_hit_rate=r.expected_term_hit_rate,
                avg_latency_ms=r.avg_latency_ms,
                top_hits=r.top_hits,
                debug_info=r.debug_info,
            ))

        summary = None
        if result_items:
            n = len(result_items)
            summary = RunSummary(
                total_queries=n,
                hit_at_1_rate=round(sum(1 for x in result_items if x.hit_at_1) / n, 4),
                hit_at_3_rate=round(sum(1 for x in result_items if x.hit_at_3) / n, 4),
                hit_at_5_rate=round(sum(1 for x in result_items if x.hit_at_5) / n, 4),
                mean_mrr=round(sum(x.mrr for x in result_items) / n, 4),
                mean_term_hit_rate=round(sum(x.expected_term_hit_rate for x in result_items) / n, 4),
                mean_latency_ms=int(sum(x.avg_latency_ms for x in result_items) / n),
            )

        return RunDetailResponse(
            run_uuid=str(run.run_uuid),
            dataset_uuid=str(run.dataset_uuid),
            chunking_strategy=run.chunking_strategy,
            chunking_params=run.chunking_params,
            retrieval_strategy=run.retrieval_strategy,
            retrieval_params=run.retrieval_params,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
            results=result_items,
            summary=summary,
        )

    def delete_run(self, run_uuid: str) -> None:
        run = self._get_run(run_uuid)
        # Clean up isolated chunks
        self.session.execute(
            delete(EvaluationChunk).where(EvaluationChunk.run_uuid == run.run_uuid)
        )
        self.session.delete(run)
        self.session.commit()

    # ── Run execution (isolation) ────────────────────────────────

    def _execute_run(self, run: EvaluationRun, doc_uuids: list[str]) -> None:
        """Execute evaluation in isolated context."""
        # Optimistic lock: only pending runs can start
        if run.status != "pending":
            logger.warning("Run %s is not pending, skipping", run.run_uuid)
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        self.session.commit()

        try:
            # Step 1: Copy chunks to evaluation_chunks (isolation)
            self._copy_chunks_to_eval(run, doc_uuids)

            # Step 2: Build temporary vector index
            self._build_eval_vector_index(run)

            # Step 3: Run queries
            queries = self._get_queries(run.dataset_uuid)
            eval_collection = f"eval_{run.run_uuid}"

            for q in queries:
                self._evaluate_query(run, q, eval_collection)

            run.status = "completed"
        except Exception as exc:
            logger.exception("Run %s failed", run.run_uuid)
            run.status = "failed"
        finally:
            run.finished_at = datetime.now(timezone.utc)
            self.session.commit()

    def _copy_chunks_to_eval(self, run: EvaluationRun, doc_uuids: list[str]) -> None:
        """Copy production chunks into isolated evaluation_chunks table."""
        if doc_uuids:
            uuids = [UUID(u) for u in doc_uuids]
            stmt = select(DocumentChunk).where(DocumentChunk.doc_uuid.in_(uuids))
        else:
            stmt = select(DocumentChunk)

        chunks = list(self.session.scalars(stmt))
        for chunk in chunks:
            eval_chunk = EvaluationChunk(
                chunk_uuid=uuid4(),
                run_uuid=run.run_uuid,
                doc_uuid=chunk.doc_uuid,
                chunk_index=chunk.chunk_index,
                chunk_type=chunk.chunk_type,
                section_title=chunk.section_title,
                page_no=chunk.page_no,
                sheet_name=chunk.sheet_name,
                row_start=chunk.row_start,
                row_end=chunk.row_end,
                token_count=chunk.token_count,
                char_count=chunk.char_count,
                chunk_text=chunk.chunk_text,
                chunk_summary=chunk.chunk_summary,
                vector_id=None,
                zilliz_collection=f"eval_{run.run_uuid}",
                metadata_json={**chunk.metadata_json},
            )
            self.session.add(eval_chunk)

        self.session.commit()
        logger.info("Copied %s chunks to eval run %s", len(chunks), run.run_uuid)

    def _build_eval_vector_index(self, run: EvaluationRun) -> None:
        """Build temporary vector index for eval chunks."""
        stmt = select(EvaluationChunk).where(EvaluationChunk.run_uuid == run.run_uuid)
        chunks = list(self.session.scalars(stmt))
        if not chunks:
            return

        texts = [c.chunk_text for c in chunks]
        embeddings = self.embedding_provider.embed_texts(texts)

        metadatas = [
            {
                "chunk_uuid": str(c.chunk_uuid),
                "doc_uuid": str(c.doc_uuid),
                "run_uuid": str(c.run_uuid),
                "chunk_index": c.chunk_index,
                "section_title": c.section_title,
            }
            for c in chunks
        ]

        # Use eval_<run_uuid> as temporary collection name
        eval_collection = f"eval_{run.run_uuid}"
        self.vector_store.upsert_embeddings(
            embeddings=[e.vector for e in embeddings],
            metadatas=metadatas,
        )
        logger.info("Built vector index for eval run %s (%s chunks)", run.run_uuid, len(chunks))

    def _evaluate_query(
        self,
        run: EvaluationRun,
        query: EvaluationQuery,
        eval_collection: str,
    ) -> None:
        """Run single query evaluation and compute metrics."""
        started = time.perf_counter()

        # Build search request
        search_req = SearchRequest(
            query=query.query_text,
            top_k=5,
            strategy=run.retrieval_strategy,
            strategy_params=run.retrieval_params or None,
            user_context=UserContext(
                user_id=self.settings.evaluation_retrieval_user_id,
            ),
        )

        # Use RetrievalService for actual retrieval
        retrieval_svc = RetrievalService(self.session)
        result = retrieval_svc.search(search_req)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        # Compute hit@k
        hit_titles = [h.title for h in result.hits]
        hit_at_1 = self._hit_at_k(hit_titles, query.expected_doc_titles, 1)
        hit_at_3 = self._hit_at_k(hit_titles, query.expected_doc_titles, 3)
        hit_at_5 = self._hit_at_k(hit_titles, query.expected_doc_titles, 5)

        # Compute MRR
        mrr = self._compute_mrr(hit_titles, query.expected_doc_titles)

        # Compute term hit rate
        term_hit_rate = self._compute_term_hit_rate(result.hits, query.expected_terms)

        top_hits_json = [
            {
                "doc_uuid": h.doc_uuid,
                "chunk_uuid": h.chunk_uuid,
                "title": h.title,
                "score": h.score,
                "snippet": h.snippet[:120],
            }
            for h in result.hits
        ]

        eval_result = EvaluationResult(
            run_uuid=run.run_uuid,
            query_uuid=query.query_uuid,
            hit_at_1=hit_at_1,
            hit_at_3=hit_at_3,
            hit_at_5=hit_at_5,
            mrr=mrr,
            expected_term_hit_rate=term_hit_rate,
            avg_latency_ms=elapsed_ms,
            top_hits=top_hits_json,
            debug_info={
                "retrieval_strategy": run.retrieval_strategy,
                "latency_ms": elapsed_ms,
                "hit_count": len(result.hits),
            },
        )
        self.session.add(eval_result)
        self.session.commit()

    # ── Metrics helpers ──────────────────────────────────────────

    @staticmethod
    def _hit_at_k(hit_titles: list[str], expected_titles: list[str], k: int) -> bool:
        if not expected_titles:
            return False
        top_k = hit_titles[:k]
        return any(et.lower() in [t.lower() for t in top_k] for et in expected_titles)

    @staticmethod
    def _compute_mrr(hit_titles: list[str], expected_titles: list[str]) -> float:
        if not expected_titles:
            return 0.0
        for rank, title in enumerate(hit_titles, start=1):
            for et in expected_titles:
                if et.lower() == title.lower():
                    return round(1.0 / rank, 4)
        return 0.0

    @staticmethod
    def _compute_term_hit_rate(hits: list, expected_terms: list[str]) -> float:
        if not expected_terms or not hits:
            return 0.0
        total_hits = 0
        for term in expected_terms:
            term_lower = term.lower()
            for hit in hits:
                if term_lower in hit.snippet.lower():
                    total_hits += 1
                    break
        return round(total_hits / len(expected_terms), 4)

    # ── Internal helpers ─────────────────────────────────────────

    def _get_dataset(self, dataset_uuid: str) -> EvaluationDataset:
        stmt = select(EvaluationDataset).where(EvaluationDataset.dataset_uuid == UUID(dataset_uuid))
        ds = self.session.scalar(stmt)
        if ds is None:
            from app.core.errors import AppError, ErrorCode
            raise AppError(code=ErrorCode.DOCUMENT_NOT_FOUND, message="dataset not found", status_code=404)
        return ds

    def _get_run(self, run_uuid: str) -> EvaluationRun:
        stmt = select(EvaluationRun).where(EvaluationRun.run_uuid == UUID(run_uuid))
        run = self.session.scalar(stmt)
        if run is None:
            from app.core.errors import AppError, ErrorCode
            raise AppError(code=ErrorCode.DOCUMENT_NOT_FOUND, message="run not found", status_code=404)
        return run

    def _get_queries(self, dataset_uuid: UUID) -> list[EvaluationQuery]:
        stmt = select(EvaluationQuery).where(EvaluationQuery.dataset_uuid == dataset_uuid)
        return list(self.session.scalars(stmt))

    def _get_results(self, run_uuid: UUID) -> list[EvaluationResult]:
        stmt = select(EvaluationResult).where(EvaluationResult.run_uuid == run_uuid)
        return list(self.session.scalars(stmt))

    def _count_queries(self, dataset_uuid: UUID) -> int:
        stmt = select(func.count(EvaluationQuery.id)).where(EvaluationQuery.dataset_uuid == dataset_uuid)
        return self.session.scalar(stmt) or 0
