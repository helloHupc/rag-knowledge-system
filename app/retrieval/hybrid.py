"""Hybrid retriever: min‑max normalization + alpha‑weighted fusion.

Combines dense (vector) and sparse (BM25) hits into a single ranked list.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DenseHit:
    chunk_uuid: str
    doc_uuid: str
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class SparseHit:
    chunk_uuid: str
    doc_uuid: str
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class HybridHit:
    chunk_uuid: str
    doc_uuid: str
    dense_score: float | None
    sparse_score: float | None
    fusion_score: float
    metadata: dict = field(default_factory=dict)


class HybridRetriever:
    """Fuses dense and sparse result lists via min‑max normalization + alpha blending.

    alpha: weight for dense scores. (1 - alpha) for sparse scores.
    """

    def __init__(self, alpha: float = 0.7) -> None:
        self.alpha = max(0.0, min(1.0, alpha))

    def fuse(
        self,
        dense_hits: list[DenseHit],
        sparse_hits: list[SparseHit],
    ) -> list[HybridHit]:
        if not dense_hits and not sparse_hits:
            return []
        if not dense_hits:
            return [
                HybridHit(
                    chunk_uuid=h.chunk_uuid,
                    doc_uuid=h.doc_uuid,
                    dense_score=None,
                    sparse_score=h.score,
                    fusion_score=h.score,
                    metadata=h.metadata,
                )
                for h in sparse_hits
            ]
        if not sparse_hits:
            return [
                HybridHit(
                    chunk_uuid=h.chunk_uuid,
                    doc_uuid=h.doc_uuid,
                    dense_score=h.score,
                    sparse_score=None,
                    fusion_score=h.score,
                    metadata=h.metadata,
                )
                for h in dense_hits
            ]

        dense_scores = [h.score for h in dense_hits]
        sparse_scores = [h.score for h in sparse_hits]

        d_min, d_max = min(dense_scores), max(dense_scores)
        s_min, s_max = min(sparse_scores), max(sparse_scores)

        d_range = d_max - d_min if d_max != d_min else 1.0
        s_range = s_max - s_min if s_max != s_min else 1.0

        # Build lookup by chunk_uuid
        dense_map: dict[str, DenseHit] = {h.chunk_uuid: h for h in dense_hits}
        sparse_map: dict[str, SparseHit] = {h.chunk_uuid: h for h in sparse_hits}

        all_uuids = set(dense_map.keys()) | set(sparse_map.keys())
        fused: list[HybridHit] = []
        for uid in all_uuids:
            d = dense_map.get(uid)
            s = sparse_map.get(uid)
            d_norm = (d.score - d_min) / d_range if d else 0.0
            s_norm = (s.score - s_min) / s_range if s else 0.0
            fusion_score = self.alpha * d_norm + (1 - self.alpha) * s_norm
            metadata = {}
            if d:
                metadata.update(d.metadata)
            if s:
                metadata.update(s.metadata)
            fused.append(
                HybridHit(
                    chunk_uuid=uid,
                    doc_uuid=(d and d.doc_uuid) or (s and s.doc_uuid) or "",
                    dense_score=d.score if d else None,
                    sparse_score=s.score if s else None,
                    fusion_score=round(fusion_score, 6),
                    metadata=metadata,
                )
            )

        fused.sort(key=lambda h: h.fusion_score, reverse=True)
        return fused
