"""Self-implemented BM25 sparse index with singleton pattern.

k1=1.2, b=0.75. Supports build_index, search, add_document, remove_document.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass(slots=True)
class SparseHit:
    """A single sparse retrieval hit."""

    chunk_uuid: str
    doc_uuid: str
    chunk_text: str
    score: float
    metadata: dict = field(default_factory=dict)


class BM25Index:
    """BM25 inverted index backed by in‑memory dicts."""

    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        # document_id → list of terms
        self._docs: dict[str, list[str]] = {}
        # term → {doc_id → term frequency}
        self._inverted: dict[str, dict[str, int]] = defaultdict(dict)
        # doc_id → chunk metadata
        self._metadata: dict[str, dict] = {}
        self._doc_count = 0
        self._total_term_count = 0
        self._avgdl: float = 0.0

    @property
    def doc_count(self) -> int:
        return self._doc_count

    @property
    def document_ids(self) -> set[str]:
        return set(self._docs.keys())

    def build_index(self, documents: list[dict]) -> None:
        """Build full index from list of document dicts.

        Each dict must have: chunk_uuid, doc_uuid, chunk_text, metadata (optional).
        """
        self._docs.clear()
        self._inverted.clear()
        self._metadata.clear()
        self._doc_count = 0
        self._total_term_count = 0

        for doc in documents:
            self.add_document(doc)

    def add_document(self, doc: dict) -> None:
        """Add or update a single document."""
        chunk_uuid = doc["chunk_uuid"]
        text = doc.get("chunk_text", "")
        tokens = self._tokenize(text)

        # Remove old entries if re‑indexing
        if chunk_uuid in self._docs:
            self._remove_from_inverted(chunk_uuid)

        self._docs[chunk_uuid] = tokens
        self._metadata[chunk_uuid] = {
            "doc_uuid": doc.get("doc_uuid", ""),
            "chunk_text": text,
            "chunk_uuid": chunk_uuid,
            **(doc.get("metadata") or {}),
        }
        self._doc_count = len(self._docs)
        self._total_term_count += len(tokens)
        self._avgdl = self._total_term_count / max(self._doc_count, 1)

        for term in tokens:
            self._inverted[term].setdefault(chunk_uuid, 0)
            self._inverted[term][chunk_uuid] += 1

    def remove_document(self, chunk_uuid: str) -> None:
        """Remove a document from the index."""
        if chunk_uuid not in self._docs:
            return
        self._remove_from_inverted(chunk_uuid)
        self._docs.pop(chunk_uuid, None)
        self._metadata.pop(chunk_uuid, None)
        self._doc_count = len(self._docs)

        token_count = sum(len(tokens) for tokens in self._docs.values())
        self._total_term_count = token_count
        self._avgdl = self._total_term_count / max(self._doc_count, 1)

    def search(self, query: str, top_k: int = 20) -> list[SparseHit]:
        """Search with BM25 scoring. Returns top‑k hits."""
        query_tokens = self._tokenize(query)
        if not query_tokens or self._doc_count == 0:
            return []

        scores: dict[str, float] = {}
        for term in query_tokens:
            posting = self._inverted.get(term, {})
            idf = self._idf(term)
            if idf == 0.0:
                continue
            for doc_id, tf in posting.items():
                doc_len = len(self._docs.get(doc_id, []))
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self._avgdl, 1))
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * numerator / denominator

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            SparseHit(
                chunk_uuid=doc_id,
                doc_uuid=self._metadata.get(doc_id, {}).get("doc_uuid", ""),
                chunk_text=self._metadata.get(doc_id, {}).get("chunk_text", ""),
                score=round(score, 6),
                metadata=self._metadata.get(doc_id, {}),
            )
            for doc_id, score in ranked
        ]

    def _remove_from_inverted(self, chunk_uuid: str) -> None:
        tokens = self._docs.get(chunk_uuid, [])
        self._total_term_count -= len(tokens)
        for term in tokens:
            posting = self._inverted.get(term)
            if posting is None:
                continue
            if chunk_uuid in posting:
                del posting[chunk_uuid]
            if not posting:
                del self._inverted[term]

    def _idf(self, term: str) -> float:
        df = len(self._inverted.get(term, {}))
        if df == 0:
            return 0.0
        return math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1.0)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer with CJK bigram support."""
        text = text.lower().strip()
        tokens: list[str] = []
        # Extract CJK bigrams
        cjk_chars = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i : i + 2])
        # Extract ASCII tokens
        ascii_text = re.sub(r"[\u4e00-\u9fff]", " ", text)
        ascii_tokens = re.findall(r"[a-z0-9]+", ascii_text)
        tokens.extend(ascii_tokens)
        return tokens


class SparseIndexProvider:
    """Thread‑safe singleton wrapper around BM25Index."""

    _instance: SparseIndexProvider | None = None
    _lock: Lock = Lock()

    def __init__(self) -> None:
        if not hasattr(self, "_index"):
            self._index = BM25Index(k1=1.2, b=0.75)

    def __new__(cls) -> SparseIndexProvider:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def index(self) -> BM25Index:
        return self._index

    def build_index(self, documents: list[dict]) -> None:
        with self._lock:
            self._index.build_index(documents)

    def search(self, query: str, top_k: int = 20) -> list[SparseHit]:
        with self._lock:
            return self._index.search(query, top_k)

    def add_document(self, doc: dict) -> None:
        with self._lock:
            self._index.add_document(doc)

    def remove_document(self, chunk_uuid: str) -> None:
        with self._lock:
            self._index.remove_document(chunk_uuid)

    @property
    def doc_count(self) -> int:
        with self._lock:
            return self._index.doc_count

    @property
    def document_ids(self) -> set[str]:
        with self._lock:
            return self._index.document_ids
