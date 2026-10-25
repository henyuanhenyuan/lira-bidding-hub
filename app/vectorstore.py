from __future__ import annotations

import atexit
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

log = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("6f1c2a5e-9f3b-5a7d-8c1e-2b4d6f8a0c3e")
_client: QdrantClient | None = None


@dataclass(frozen=True)
class Point:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    id: str
    score: float
    payload: dict[str, Any]


def default_client() -> QdrantClient:
    """URL 优先（服务端）；否则本地目录模式，Windows 单进程可用。"""
    global _client
    if _client is None:
        url = os.getenv("LIRA_QDRANT_URL", "")
        if url:
            _client = QdrantClient(url=url)
        else:
            from . import config

            path = config.DATA_DIR / "qdrant"
            path.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(path))
    return _client


def _close_client() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


atexit.register(_close_client)


def _point_uuid(collection: str, point_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{collection}:{point_id}"))


class QdrantVectorStore:
    def __init__(self, client: QdrantClient | None = None) -> None:
        self.client = client or default_client()
        self._dims: dict[str, int] = {}

    def ensure(self, collection: str, dim: int) -> None:
        known = self._dims.get(collection)
        if known is not None:
            if known != dim:
                raise ValueError(
                    f"collection {collection} 维度是 {known}，收到 {dim}"
                )
            return
        if self.client.collection_exists(collection):
            info = self.client.get_collection(collection)
            params = info.config.params.vectors
            size = getattr(params, "size", None)
            if size is not None and size != dim:
                raise ValueError(
                    f"collection {collection} 维度是 {size}，收到 {dim}"
                )
            self._dims[collection] = dim
            return
        self.client.create_collection(
            collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        self._dims[collection] = dim

    def upsert(self, collection: str, points: Iterable[Point]) -> None:
        batch = list(points)
        if not batch:
            return
        dim = len(batch[0].vector)
        if any(len(p.vector) != dim for p in batch):
            raise ValueError("同一批次的向量维度必须一致")
        self.ensure(collection, dim)
        self.client.upsert(
            collection,
            points=[
                PointStruct(
                    id=_point_uuid(collection, p.id),
                    vector=p.vector,
                    payload={**p.payload, "ref": p.id},
                )
                for p in batch
            ],
        )

    def search(
        self,
        collection: str,
        vector: list[float],
        *,
        top_k: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        if not self.client.collection_exists(collection):
            return []
        query_filter = None
        if filters:
            query_filter = Filter(
                must=[
                    FieldCondition(key=key, match=MatchValue(value=value))
                    for key, value in filters.items()
                ]
            )
        response = self.client.query_points(
            collection,
            query=vector,
            limit=max(1, top_k),
            query_filter=query_filter,
            with_payload=True,
        )
        hits: list[Hit] = []
        for point in response.points:
            payload = dict(point.payload or {})
            hits.append(
                Hit(
                    id=payload.get("ref", str(point.id)),
                    score=float(point.score),
                    payload=payload,
                )
            )
        return hits

    def delete(self, collection: str, ids: Iterable[str]) -> None:
        if not self.client.collection_exists(collection):
            return
        self.client.delete(
            collection,
            points_selector=PointIdsList(
                points=[_point_uuid(collection, i) for i in ids]
            ),
        )

    def count(self, collection: str) -> int:
        if not self.client.collection_exists(collection):
            return 0
        return int(self.client.count(collection).count)
