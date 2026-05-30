from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.trace import get_trace_id
from app.integrations.embedding import EmbeddingProvider
from app.integrations.rerank import create_rerank_provider, BaseRerankProvider
from app.integrations.vector_store import VectorStoreClient
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.retrieval_log import RetrievalLog
from app.permissions.loader import load_permission_checker
from app.repositories.retrieval_logs import RetrievalLogRepository
from app.retrieval.hybrid import HybridRetriever, DenseHit as _DenseHit, SparseHit as _SparseHit
from app.retrieval.sparse_index import SparseIndexProvider
from app.schemas.retrieval import (
    Citation,
    DebugSearchResponseData,
    DenseHitDebug,
    SparseHitDebug,
    RetrievalFilters,
    SearchRequest,
    SearchResponseData,
    UserContext,
)
from app.services.sparse_indexing import SparseIndexingService


logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.embedding_provider = EmbeddingProvider(self.settings)
        self.vector_store = VectorStoreClient(self.settings)
        self.logs = RetrievalLogRepository(session)
        self.permission_checker = load_permission_checker()
        self.sparse_index = SparseIndexProvider()
        self.sparse_indexing = SparseIndexingService()
        self.hybrid = HybridRetriever(alpha=0.7)
        self.rerank_provider: BaseRerankProvider | None = None

    def search(
        self,
        request: SearchRequest,
        *,
        trusted_user_context: bool = False,
        authenticated_identity_required: bool = False,
    ) -> SearchResponseData:
        started = time.perf_counter()
        
        # 用户身份解析（简化，不再强制要求）
        user_context = request.user_context
        
        # 如果需要认证身份但未提供，返回错误
        if authenticated_identity_required and (not user_context or not user_context.is_authenticated):
            raise AppError(
                code=ErrorCode.AUTHENTICATION_FAILED,
                message="authenticated identity is required",
                status_code=401,
            )
        
        self._last_user_context = user_context
        rewritten_query = self._rewrite_query(request.query)
        documents = self._load_documents(filters=request.filters)
        
        # 权限过滤（使用新的权限检查器）
        allowed_documents = self._resolve_allowed_documents(
            documents=documents,
            user_context=user_context,
        )
        
        if not allowed_documents:
            return self._build_empty_response(request, rewritten_query, started)

        strategy = request.strategy or "dense"
        if strategy == "hybrid":
            return self._search_hybrid(request, rewritten_query, allowed_documents, started)
        return self._search_dense(request, rewritten_query, allowed_documents, started)

    def debug_search(
        self,
        request: SearchRequest,
        *,
        authenticated_identity_required: bool = False,
    ) -> DebugSearchResponseData:
        result = self.search(
            request,
            authenticated_identity_required=authenticated_identity_required,
        )
        strategy = request.strategy or "dense"

        ranking_debug = [
            {
                "chunk_uuid": citation.chunk_uuid,
                "doc_uuid": citation.doc_uuid,
                "score": citation.score,
                "vector_score": citation.vector_score,
                "text_score": citation.text_score,
                "sparse_score": citation.sparse_score,
                "rerank_score": citation.rerank_score,
                "pre_rerank_score": citation.pre_rerank_score,
                "section_title": citation.section_title,
            }
            for citation in result.hits
        ]

        rerank_info = self._get_rerank_info()

        return DebugSearchResponseData(
            **result.model_dump(),
            raw_filters=self._filters_to_dict(request.filters),
            user_context=(getattr(self, '_last_user_context', None) or request.user_context or UserContext(user_id='anonymous')).model_dump(),
            ranking_debug=ranking_debug,
            retrieval_strategy=strategy,
            dense_hits=getattr(self, "_last_dense_hits_debug", []),
            sparse_hits=getattr(self, "_last_sparse_hits_debug", []),
            fusion_alpha=0.7 if strategy == "hybrid" else None,
            rerank_enabled=rerank_info[0],
            rerank_model=rerank_info[1],
            rerank_latency_ms=rerank_info[2],
        )

    # ── dense search ──────────────────────────────────────────────

    def _search_dense(
        self,
        request: SearchRequest,
        rewritten_query: str,
        allowed_documents: dict[str, Document],
        started: float,
    ) -> SearchResponseData:
        query_embedding = self.embedding_provider.embed_texts([rewritten_query])[0].vector
        vector_filters = self._build_vector_filters(request.filters, allowed_documents)
        vector_hits = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k * 3,
            filters=vector_filters,
        )
        chunk_ids = [hit.metadata.get("chunk_uuid") for hit in vector_hits if hit.metadata.get("chunk_uuid")]
        chunks_by_uuid = self._load_chunks_by_uuid(chunk_ids)
        ranked = []
        for hit in vector_hits:
            chunk_uuid = hit.metadata.get("chunk_uuid")
            if not chunk_uuid:
                continue
            chunk = chunks_by_uuid.get(chunk_uuid)
            if chunk is None:
                continue
            document = allowed_documents.get(str(chunk.doc_uuid))
            if document is None:
                continue
            vector_score = max(hit.score, 0.0)
            if vector_score < request.min_score:
                continue
            ranked.append((vector_score, document, chunk))

        ranked.sort(key=lambda item: item[0], reverse=True)

        # Apply rerank if enabled
        rerank_latency = 0
        rerank_scores: dict[str, tuple[float, float]] = {}  # chunk_uuid → (rerank_score, pre_rerank)
        if self._is_rerank_enabled():
            rr_started = time.perf_counter()
            ranked = self._apply_rerank_dense(ranked, rewritten_query)
            rerank_latency = int((time.perf_counter() - rr_started) * 1000)
            self._last_rerank_latency = rerank_latency
            for item in ranked:
                chunk_uuid = str(item[2].chunk_uuid)
                rerank_scores[chunk_uuid] = (item[0], 0.0)

        top_hits = ranked[: request.top_k]
        
        # 图片文件扩展名
        IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp"}
        
        citations = [
            Citation(
                doc_uuid=str(document.doc_uuid),
                chunk_uuid=str(chunk.chunk_uuid),
                title=document.title,
                source_module=document.source_module,
                page_no=chunk.page_no,
                sheet_name=chunk.sheet_name,
                section_title=chunk.section_title,
                snippet=chunk.chunk_text[:240],
                version=document.version,
                updated_at=document.updated_at,
                score=vector_score,
                vector_score=vector_score,
                text_score=None,
                rerank_score=rerank_scores.get(str(chunk.chunk_uuid), (None, None))[0],
                pre_rerank_score=rerank_scores.get(str(chunk.chunk_uuid), (None, None))[1],
                image_url=f"/api/v1/documents/{document.doc_uuid}/download" if document.file_ext in IMAGE_EXTENSIONS else None,
            )
            for vector_score, document, chunk in top_hits
        ]

        # Store debug hits
        self._last_dense_hits_debug = [
            DenseHitDebug(chunk_uuid=str(chunk.chunk_uuid), doc_uuid=str(document.doc_uuid), score=vector_score)
            for vector_score, _, chunk in ranked[:request.top_k * 3]
        ]
        self._last_sparse_hits_debug = []
        self._last_rerank_latency = rerank_latency

        latency_ms = int((time.perf_counter() - started) * 1000)
        filters_applied = self._filters_to_dict(request.filters)
        self._log_search(
            request=request,
            rewritten_query=rewritten_query,
            hit_count=len(citations),
            filters_applied=filters_applied,
            citations=citations,
            latency_ms=latency_ms,
        )
        return SearchResponseData(
            query=request.query,
            rewritten_query=rewritten_query,
            filters_applied=filters_applied,
            hits=citations,
            latency_ms=latency_ms,
        )

    # ── hybrid search ─────────────────────────────────────────────

    def _search_hybrid(
        self,
        request: SearchRequest,
        rewritten_query: str,
        allowed_documents: dict[str, Document],
        started: float,
    ) -> SearchResponseData:
        self.sparse_indexing.ensure_database_indexed(self.session)
        # Dense recall
        query_embedding = self.embedding_provider.embed_texts([rewritten_query])[0].vector
        vector_filters = self._build_vector_filters(request.filters, allowed_documents)
        vector_hits = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k * 3,
            filters=vector_filters,
        )
        # Sparse recall
        sparse_hits = self.sparse_index.search(rewritten_query, top_k=request.top_k * 3)

        # Filter sparse hits against allowed documents
        chunk_ids = [hit.metadata.get("chunk_uuid") for hit in vector_hits if hit.metadata.get("chunk_uuid")]
        sparse_chunk_ids = [h.chunk_uuid for h in sparse_hits]
        all_chunk_ids = list(set(chunk_ids + sparse_chunk_ids))
        chunks_by_uuid = self._load_chunks_by_uuid(all_chunk_ids)

        # Build dense hit list
        dense_hits = []
        for hit in vector_hits:
            chunk_uuid = hit.metadata.get("chunk_uuid")
            if not chunk_uuid:
                continue
            chunk = chunks_by_uuid.get(chunk_uuid)
            if chunk is None:
                continue
            doc = allowed_documents.get(str(chunk.doc_uuid))
            if doc is None:
                continue
            dense_hits.append(_DenseHit(
                chunk_uuid=chunk_uuid,
                doc_uuid=str(chunk.doc_uuid),
                score=max(hit.score, 0.0),
                metadata={"chunk": chunk, "document": doc},
            ))

        # Build sparse hit list
        sparse_hitlist = []
        for h in sparse_hits:
            chunk = chunks_by_uuid.get(h.chunk_uuid)
            if chunk is None:
                continue
            doc = allowed_documents.get(str(chunk.doc_uuid))
            if doc is None:
                continue
            sparse_hitlist.append(_SparseHit(
                chunk_uuid=h.chunk_uuid,
                doc_uuid=str(chunk.doc_uuid),
                score=h.score,
                metadata={"chunk": chunk, "document": doc},
            ))

        # Fuse
        fused = self.hybrid.fuse(dense_hits, sparse_hitlist)

        # Apply min_score filter and map to ranked tuples
        ranked = []
        for h in fused:
            chunk = chunks_by_uuid.get(h.chunk_uuid)
            if chunk is None:
                continue
            doc = allowed_documents.get(str(chunk.doc_uuid))
            if doc is None:
                continue
            if h.fusion_score < request.min_score:
                continue
            ranked.append((h.fusion_score, h.dense_score or 0.0, h.sparse_score or 0.0, doc, chunk))

        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

        # Rerank if enabled
        rerank_latency = 0
        rerank_scores: dict[str, tuple[float, float]] = {}
        if self._is_rerank_enabled():
            rr_started = time.perf_counter()
            for i in range(len(ranked)):
                score, dense_s, sparse_s, doc, chunk = ranked[i]
                rerank_scores[str(chunk.chunk_uuid)] = (score, 0.0)  # pre_rerank stored before rerank
            ranked = self._apply_rerank_hybrid(ranked, rewritten_query)
            rerank_latency = int((time.perf_counter() - rr_started) * 1000)
            self._last_rerank_latency = rerank_latency

        top_hits = ranked[: request.top_k]
        
        # 图片文件扩展名
        IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp"}
        
        citations = [
            Citation(
                doc_uuid=str(document.doc_uuid),
                chunk_uuid=str(chunk.chunk_uuid),
                title=document.title,
                source_module=document.source_module,
                page_no=chunk.page_no,
                sheet_name=chunk.sheet_name,
                section_title=chunk.section_title,
                snippet=chunk.chunk_text[:240],
                version=document.version,
                updated_at=document.updated_at,
                score=final_score,
                vector_score=dense_score,
                text_score=None,
                sparse_score=sparse_score,
                rerank_score=rerank_scores.get(str(chunk.chunk_uuid), (None, None))[0],
                pre_rerank_score=rerank_scores.get(str(chunk.chunk_uuid), (None, None))[1],
                image_url=f"/api/v1/documents/{document.doc_uuid}/download" if document.file_ext in IMAGE_EXTENSIONS else None,
            )
            for final_score, dense_score, sparse_score, document, chunk in top_hits
        ]

        # Debug hits
        self._last_dense_hits_debug = [
            DenseHitDebug(chunk_uuid=h.chunk_uuid, doc_uuid=h.doc_uuid, score=h.score)
            for h in dense_hits[:20]
        ]
        self._last_sparse_hits_debug = [
            SparseHitDebug(chunk_uuid=h.chunk_uuid, doc_uuid=h.doc_uuid, score=h.score)
            for h in sparse_hitlist[:20]
        ]
        self._last_rerank_latency = rerank_latency

        latency_ms = int((time.perf_counter() - started) * 1000)
        filters_applied = self._filters_to_dict(request.filters)
        self._log_search(
            request=request,
            rewritten_query=rewritten_query,
            hit_count=len(citations),
            filters_applied=filters_applied,
            citations=citations,
            latency_ms=latency_ms,
        )
        return SearchResponseData(
            query=request.query,
            rewritten_query=rewritten_query,
            filters_applied=filters_applied,
            hits=citations,
            latency_ms=latency_ms,
        )

    # ── rerank ────────────────────────────────────────────────────

    def _is_rerank_enabled(self) -> bool:
        return bool(
            self.settings.rerank_enabled
            and self.settings.rerank_api_base
            and self.settings.rerank_api_key
        )

    def _get_rerank_provider(self) -> BaseRerankProvider:
        if self.rerank_provider is None:
            self.rerank_provider = create_rerank_provider(self.settings)
        return self.rerank_provider

    def _get_rerank_info(self) -> tuple[bool, str | None, int | None]:
        enabled = self._is_rerank_enabled()
        model = self.settings.rerank_model if enabled else None
        latency = getattr(self, "_last_rerank_latency", None)
        return (enabled, model, latency)

    def _apply_rerank_dense(
        self,
        ranked: list[tuple[float, Document, DocumentChunk]],
        rewritten_query: str,
    ) -> list[tuple[float, Document, DocumentChunk]]:
        """Rerank dense results. Graceful fallback on error."""
        try:
            provider = self._get_rerank_provider()
            documents = [item[2].chunk_text[:800] for item in ranked]
            results = provider.rerank(rewritten_query, documents, top_n=len(ranked))
            reranked = []
            for r in results:
                if r.index < len(ranked):
                    original = ranked[r.index]
                    reranked.append((r.score, original[1], original[2]))
            if not reranked:
                return ranked
            return reranked
        except Exception:
            logger.exception("Rerank failed, using original scores")
            return ranked

    def _apply_rerank_hybrid(
        self,
        ranked: list[tuple[float, float, float, Document, DocumentChunk]],
        rewritten_query: str,
    ) -> list[tuple[float, float, float, Document, DocumentChunk]]:
        """Rerank hybrid results. Graceful fallback on error."""
        try:
            provider = self._get_rerank_provider()
            documents = [item[4].chunk_text[:800] for item in ranked]
            results = provider.rerank(rewritten_query, documents, top_n=len(ranked))
            reranked = []
            for r in results:
                if r.index < len(ranked):
                    original = ranked[r.index]
                    reranked.append((r.score, original[1], original[2], original[3], original[4]))
            if not reranked:
                return ranked
            return reranked
        except Exception:
            logger.exception("Rerank failed, using original scores")
            return ranked

    # ── shared helpers ────────────────────────────────────────────

    def _build_empty_response(self, request: SearchRequest, rewritten_query: str, started: float) -> SearchResponseData:
        latency_ms = int((time.perf_counter() - started) * 1000)
        filters_applied = self._filters_to_dict(request.filters)
        self._log_search(
            request=request,
            rewritten_query=rewritten_query,
            hit_count=0,
            filters_applied=filters_applied,
            citations=[],
            latency_ms=latency_ms,
        )
        self._last_dense_hits_debug = []
        self._last_sparse_hits_debug = []
        return SearchResponseData(
            query=request.query,
            rewritten_query=rewritten_query,
            filters_applied=filters_applied,
            hits=[],
            latency_ms=latency_ms,
        )

    def _load_documents(self, filters: RetrievalFilters | None) -> list[Document]:
        stmt = select(Document).where(Document.deleted_at.is_(None))
        if filters is not None:
            if filters.source_module:
                normalized_modules = [item.strip().lower() for item in filters.source_module if item and item.strip()]
                if normalized_modules:
                    stmt = stmt.where(func.lower(Document.source_module).in_(normalized_modules))
            if filters.source_type:
                normalized_types = [item.strip().lower() for item in filters.source_type if item and item.strip()]
                if normalized_types:
                    stmt = stmt.where(func.lower(Document.source_type).in_(normalized_types))
            if filters.file_ext:
                normalized_exts = [item.strip().lower() for item in filters.file_ext if item and item.strip()]
                if normalized_exts:
                    stmt = stmt.where(func.lower(Document.file_ext).in_(normalized_exts))
            if filters.date_from:
                stmt = stmt.where(Document.created_at >= filters.date_from)
            if filters.date_to:
                stmt = stmt.where(Document.created_at <= filters.date_to)
        return list(self.session.scalars(stmt))

    def _load_chunks_by_uuid(self, chunk_uuids: list[str]) -> dict[str, DocumentChunk]:
        if not chunk_uuids:
            return {}
        normalized = []
        for chunk_uuid in chunk_uuids:
            if not chunk_uuid:
                continue
            try:
                normalized.append(UUID(str(chunk_uuid)))
            except ValueError:
                logger.warning("Skipping invalid chunk_uuid from retrieval index: %s", chunk_uuid)
        if not normalized:
            return {}
        stmt = select(DocumentChunk).where(DocumentChunk.chunk_uuid.in_(normalized))
        chunks = list(self.session.scalars(stmt))
        return {str(chunk.chunk_uuid): chunk for chunk in chunks}

    def _resolve_allowed_documents(
        self,
        *,
        documents: list[Document],
        user_context: UserContext | None,
    ) -> dict[str, Document]:
        """使用权限检查器过滤文档"""
        # 如果权限模式为无权限检查，直接返回所有文档
        if self.settings.permission_mode == "none":
            return {str(doc.doc_uuid): doc for doc in documents}
        
        # 将 Document 对象转换为字典
        docs_dict = [self._document_to_dict(doc) for doc in documents]
        user_context_dict = user_context.model_dump() if user_context else None
        
        # 调用权限检查器过滤
        allowed_docs_dict = self.permission_checker.filter_documents(docs_dict, user_context_dict)
        
        # 将过滤后的字典转回 Document 对象
        allowed_uuids = {d["doc_uuid"] for d in allowed_docs_dict}
        allowed_documents = {}
        for document in documents:
            doc_uuid = str(document.doc_uuid)
            if doc_uuid in allowed_uuids:
                allowed_documents[doc_uuid] = document
        
        return allowed_documents
    
    @staticmethod
    def _document_to_dict(document: Document) -> dict:
        """将 Document 对象转换为字典"""
        return {
            "doc_uuid": str(document.doc_uuid),
            "source_module": document.source_module,
            "source_type": document.source_type,
            "access_level": document.access_level,
            "tags": document.tags,
            "owner_dept": document.owner_dept,
            "created_by": document.created_by,
            "title": document.title,
            "file_ext": document.file_ext,
        }

    @staticmethod
    def _rewrite_query(query: str) -> str:
        return " ".join(query.strip().split())

    @staticmethod
    def _filters_to_dict(filters: RetrievalFilters | None) -> dict:
        return filters.model_dump(mode="json", exclude_none=True) if filters else {}

    def _build_vector_filters(self, filters: RetrievalFilters | None, allowed_documents: dict[str, Document]) -> dict:
        return {"doc_uuid": list(allowed_documents.keys())}

    def _log_search(
        self,
        *,
        request: SearchRequest,
        rewritten_query: str,
        hit_count: int,
        filters_applied: dict,
        citations: list[Citation],
        latency_ms: int,
    ) -> None:
        trace_id = get_trace_id()
        self.logs.add(
            RetrievalLog(
                trace_id=trace_id,
                query_text=request.query,
                rewritten_query=rewritten_query,
                query_intent="search",
                filters_json=filters_applied,
                user_context_json=request.user_context.model_dump() if request.user_context else {},
                top_k=request.top_k,
                hit_count=hit_count,
                retrieval_latency_ms=latency_ms,
                total_latency_ms=latency_ms,
                matched_documents_json=[
                    {
                        "doc_uuid": citation.doc_uuid,
                        "chunk_uuid": citation.chunk_uuid,
                        "score": citation.score,
                        "vector_score": citation.vector_score,
                        "text_score": citation.text_score,
                    }
                    for citation in citations
                ],
                response_excerpt=citations[0].snippet if citations else None,
            )
        )
        self.session.commit()
