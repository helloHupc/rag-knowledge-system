from __future__ import annotations

import logging
from dataclasses import dataclass
from math import sqrt
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VectorRecord:
    vector_id: str
    metadata: dict
    collection: str
    embedding: list[float] | None = None


@dataclass(slots=True)
class SearchResult:
    vector_id: str
    score: float
    metadata: dict
    collection: str


class VectorStoreClient:
    _local_store: dict[str, list[VectorRecord]] = {}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def upsert_embeddings(
        self,
        *,
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> list[VectorRecord]:
        if self._provider() == "zilliz":
            return self._upsert_zilliz_placeholder(embeddings=embeddings, metadatas=metadatas)
        return self._upsert_local(embeddings=embeddings, metadatas=metadatas)

    def search(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        if self._provider() == "zilliz":
            return self._search_zilliz_placeholder(query_embedding=query_embedding, top_k=top_k, filters=filters)
        return self._search_local(query_embedding=query_embedding, top_k=top_k, filters=filters)

    def delete_embeddings(
        self,
        *,
        chunk_ids: list[str],
    ) -> int:
        if not chunk_ids:
            return 0
        if self._provider() == "zilliz":
            return self._delete_zilliz(chunk_ids=chunk_ids)
        return self._delete_local(chunk_ids=chunk_ids)

    def probe(self) -> bool:
        if self._provider() != "zilliz":
            return True
        if not self.settings.zilliz_uri or not self.settings.zilliz_token:
            return False
        try:
            from pymilvus import MilvusClient
        except ImportError:
            return False
        try:
            client = MilvusClient(uri=self.settings.zilliz_uri, token=self.settings.zilliz_token)
            client.has_collection(collection_name=self.settings.zilliz_collection)
            return True
        except Exception:
            logger.exception("Zilliz probe failed")
            return False

    def _upsert_local(
        self,
        *,
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> list[VectorRecord]:
        records: list[VectorRecord] = []
        for metadata, embedding in zip(metadatas, embeddings, strict=True):
            record = (
                VectorRecord(
                    vector_id=f"vec_{uuid4().hex}",
                    metadata=metadata,
                    collection=self.settings.zilliz_collection,
                    embedding=embedding,
                )
            )
            records.append(record)

        existing_records = self._local_store.setdefault(self.settings.zilliz_collection, [])
        existing_records.extend(records)

        logger.info(
            "Prepared %s vector records for collection %s",
            len(records),
            self.settings.zilliz_collection,
        )
        return records

    def _search_local(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        records = self._local_store.get(self.settings.zilliz_collection, [])
        matches: list[SearchResult] = []
        for record in records:
            if not record.embedding:
                continue
            if filters and not self._metadata_matches(record.metadata, filters):
                continue
            score = self._cosine_similarity(query_embedding, record.embedding)
            matches.append(
                SearchResult(
                    vector_id=record.vector_id,
                    score=score,
                    metadata=record.metadata,
                    collection=record.collection,
                )
            )
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:top_k]

    def _delete_local(self, *, chunk_ids: list[str]) -> int:
        chunk_id_set = set(chunk_ids)
        records = self._local_store.get(self.settings.zilliz_collection, [])
        before_count = len(records)
        self._local_store[self.settings.zilliz_collection] = [
            record
            for record in records
            if str(record.metadata.get("chunk_uuid")) not in chunk_id_set
        ]
        return before_count - len(self._local_store[self.settings.zilliz_collection])

    def _upsert_zilliz_placeholder(
        self,
        *,
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> list[VectorRecord]:
        if not self.settings.zilliz_uri or not self.settings.zilliz_token:
            raise AppError(
                code=ErrorCode.VECTOR_WRITE_FAILED,
                message="zilliz provider is not configured",
                status_code=422,
            )
        try:
            from pymilvus import DataType, MilvusClient
        except ImportError as exc:
            raise AppError(
                code=ErrorCode.VECTOR_WRITE_FAILED,
                message="pymilvus is required for zilliz provider",
                status_code=500,
            ) from exc

        client = MilvusClient(uri=self.settings.zilliz_uri, token=self.settings.zilliz_token)
        self._ensure_collection(client=client, data_type_cls=DataType)

        rows = []
        for metadata, embedding in zip(metadatas, embeddings, strict=True):
            rows.append(
                {
                    "chunk_uuid": metadata["chunk_uuid"],
                    "vector": embedding,
                    **metadata,
                }
            )

        client.upsert(collection_name=self.settings.zilliz_collection, data=rows)
        return [
            VectorRecord(
                vector_id=str(metadata["chunk_uuid"]),
                metadata=metadata,
                collection=self.settings.zilliz_collection,
                embedding=embedding,
            )
            for metadata, embedding in zip(metadatas, embeddings, strict=True)
        ]

    def _delete_zilliz(self, *, chunk_ids: list[str]) -> int:
        if not self.settings.zilliz_uri or not self.settings.zilliz_token:
            raise AppError(
                code=ErrorCode.VECTOR_WRITE_FAILED,
                message="zilliz provider is not configured",
                status_code=422,
            )
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise AppError(
                code=ErrorCode.VECTOR_WRITE_FAILED,
                message="pymilvus is required for zilliz provider",
                status_code=500,
            ) from exc

        try:
            client = MilvusClient(uri=self.settings.zilliz_uri, token=self.settings.zilliz_token)
            delete_result = client.delete(
                collection_name=self.settings.zilliz_collection,
                ids=chunk_ids,
            )
            return int(delete_result.get("delete_count", 0))
        except Exception as exc:
            # Collection may not exist yet — treat as zero deletions.
            logger.warning("Zilliz delete failed (collection may not exist): %s", exc)
            return 0

    def _search_zilliz_placeholder(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        if not self.settings.zilliz_uri or not self.settings.zilliz_token:
            raise AppError(
                code=ErrorCode.RETRIEVAL_FAILED,
                message="zilliz provider is not configured",
                status_code=422,
            )
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise AppError(
                code=ErrorCode.RETRIEVAL_FAILED,
                message="pymilvus is required for zilliz provider",
                status_code=500,
            ) from exc

        try:
            client = MilvusClient(uri=self.settings.zilliz_uri, token=self.settings.zilliz_token)
            filter_expr = self._build_zilliz_filter_expression(filters)
            search_response = client.search(
                collection_name=self.settings.zilliz_collection,
                anns_field="vector",
                data=[query_embedding],
                limit=top_k,
                filter=filter_expr,
                output_fields=[
                    "chunk_uuid",
                    "doc_uuid",
                    "source_module",
                    "source_type",
                    "file_ext",
                    "version",
                    "page_no",
                    "sheet_name",
                    "section_title",
                    "access_level",
                    "owner_dept",
                ],
                search_params={"metric_type": "COSINE"},
            )
            first_result_set = search_response[0] if search_response else []
            return [
                SearchResult(
                    vector_id=str(hit.get("id") or hit.get("chunk_uuid")),
                    score=float(hit.get("distance", 0.0)),
                    metadata=self._extract_search_metadata(hit),
                    collection=self.settings.zilliz_collection,
                )
                for hit in first_result_set
            ]
        except Exception as exc:
            # Collection may not exist yet — return empty results.
            logger.warning("Zilliz search failed (collection may not exist): %s", exc)
            return []

    def _provider(self) -> str:
        return self.settings.vector_store_provider.lower()

    def _ensure_collection(self, *, client, data_type_cls) -> None:
        if client.has_collection(collection_name=self.settings.zilliz_collection):
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(
            field_name="chunk_uuid",
            datatype=data_type_cls.VARCHAR,
            is_primary=True,
            max_length=64,
        )
        schema.add_field(
            field_name="vector",
            datatype=data_type_cls.FLOAT_VECTOR,
            dim=self.settings.embedding_vector_size,
        )
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        client.create_collection(
            collection_name=self.settings.zilliz_collection,
            schema=schema,
            index_params=index_params,
        )

    @staticmethod
    def _metadata_matches(metadata: dict, filters: dict) -> bool:
        for key, value in filters.items():
            if value is None:
                continue
            candidate = metadata.get(key)
            if isinstance(value, list):
                if candidate not in value:
                    return False
            else:
                if candidate != value:
                    return False
        return True

    @staticmethod
    def _build_zilliz_filter_expression(filters: dict | None) -> str:
        if not filters:
            return ""

        expressions: list[str] = []
        for key, value in filters.items():
            if value is None:
                continue
            if isinstance(value, list):
                normalized_values = [item for item in value if item is not None]
                if not normalized_values:
                    continue
                rendered_items = ", ".join(
                    VectorStoreClient._render_zilliz_literal(item)
                    for item in normalized_values
                )
                expressions.append(f"{key} in [{rendered_items}]")
            else:
                expressions.append(f"{key} == {VectorStoreClient._render_zilliz_literal(value)}")
        return " and ".join(expressions)

    @staticmethod
    def _render_zilliz_literal(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _extract_search_metadata(hit: dict) -> dict:
        entity = hit.get("entity")
        metadata: dict = {}
        if isinstance(entity, dict):
            metadata.update(entity)
        for key in (
            "chunk_uuid",
            "doc_uuid",
            "source_module",
            "source_type",
            "file_ext",
            "version",
            "page_no",
            "sheet_name",
            "section_title",
            "access_level",
            "owner_dept",
        ):
            if key in hit and hit.get(key) is not None:
                metadata[key] = hit.get(key)
        if "chunk_uuid" not in metadata:
            metadata["chunk_uuid"] = str(hit.get("id"))
        return metadata

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = sqrt(sum(x * x for x in a))
        norm_b = sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return round(dot / (norm_a * norm_b), 6)
