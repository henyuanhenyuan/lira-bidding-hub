from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import db

log = logging.getLogger(__name__)

_DIMS: dict[str, int] = {}
_SAFE = re.compile(r"[^a-z0-9_]")
_DIM_RE = re.compile(r"vector\((\d+)\)")


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


def table_name(collection: str) -> str:
    safe = _SAFE.sub("_", (collection or "").lower()).strip("_")
    if not safe:
        raise ValueError("collection 不能为空")
    if len(safe) > 48:
        digest = hashlib.md5(collection.encode("utf-8")).hexdigest()[:8]
        safe = f"{safe[:39]}_{digest}"
    return f"vec_{safe}"


def _literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.7g}" for value in vector) + "]"


def _exists(conn, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(?) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _column_dim(conn, table: str) -> int | None:
    row = conn.execute(
        "SELECT format_type(a.atttypid, a.atttypmod) AS t"
        " FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
        " WHERE c.relname = ? AND a.attname = 'embedding' AND NOT a.attisdropped",
        (table,),
    ).fetchone()
    if not row:
        return None
    match = _DIM_RE.search(row["t"] or "")
    return int(match.group(1)) if match else None


class PgVectorStore:
    """PostgreSQL + pgvector 向量存储：每集合一张表，HNSW 余弦索引。"""

    def ensure(self, collection: str, dim: int) -> str:
        table = table_name(collection)
        known = _DIMS.get(collection)
        if known is not None:
            if known != dim:
                raise ValueError(f"collection {collection} 维度是 {known}，收到 {dim}")
            return table
        with db.get_db() as conn:
            if _exists(conn, table):
                size = _column_dim(conn, table)
                if size is not None and size != dim:
                    raise ValueError(
                        f"collection {collection} 维度是 {size}，收到 {dim}"
                    )
            else:
                conn.execute(
                    f'CREATE TABLE IF NOT EXISTS "{table}" ('
                    " id TEXT PRIMARY KEY,"
                    f" embedding vector({int(dim)}) NOT NULL,"
                    " payload JSONB NOT NULL DEFAULT '{}'::jsonb)"
                )
                index = f"{table}_hnsw"[:63]
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}"'
                    " USING hnsw (embedding vector_cosine_ops)"
                )
        _DIMS[collection] = int(dim)
        return table

    def upsert(self, collection: str, points: Iterable[Point]) -> None:
        batch = list(points)
        if not batch:
            return
        dim = len(batch[0].vector)
        if any(len(point.vector) != dim for point in batch):
            raise ValueError("同一批次的向量维度必须一致")
        table = self.ensure(collection, dim)
        rows = [
            (point.id, _literal(point.vector), json.dumps(point.payload, ensure_ascii=False))
            for point in batch
        ]
        with db.get_db() as conn:
            conn.executemany(
                f'INSERT INTO "{table}" (id, embedding, payload) VALUES (?,?::vector,?::jsonb)'
                " ON CONFLICT (id) DO UPDATE SET"
                " embedding = EXCLUDED.embedding, payload = EXCLUDED.payload",
                rows,
            )

    def search(
        self,
        collection: str,
        vector: list[float],
        *,
        top_k: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        table = table_name(collection)
        query = _literal(vector)
        with db.get_db() as conn:
            if not _exists(conn, table):
                return []
            if filters:
                sql = (
                    f'SELECT id, payload, 1 - (embedding <=> ?::vector) AS score'
                    f' FROM "{table}" WHERE payload @> ?::jsonb'
                    " ORDER BY embedding <=> ?::vector LIMIT ?"
                )
                rows = conn.execute(
                    sql,
                    (query, json.dumps(filters, ensure_ascii=False), query, max(1, top_k)),
                ).fetchall()
            else:
                sql = (
                    f'SELECT id, payload, 1 - (embedding <=> ?::vector) AS score'
                    f' FROM "{table}" ORDER BY embedding <=> ?::vector LIMIT ?'
                )
                rows = conn.execute(sql, (query, query, max(1, top_k))).fetchall()
        return [
            Hit(id=row["id"], score=float(row["score"]), payload=dict(row["payload"] or {}))
            for row in rows
        ]

    def delete(self, collection: str, ids: Iterable[str]) -> None:
        table = table_name(collection)
        keys = list(ids)
        if not keys:
            return
        with db.get_db() as conn:
            if _exists(conn, table):
                conn.execute(f'DELETE FROM "{table}" WHERE id = ANY(?)', (keys,))

    def collections(self, prefix: str = "") -> list[str]:
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_name LIKE 'vec\\_%'"
            ).fetchall()
        names = [row["table_name"][4:] for row in rows]
        return sorted(name for name in names if name.startswith(prefix))

    def count(self, collection: str) -> int:
        table = table_name(collection)
        with db.get_db() as conn:
            if not _exists(conn, table):
                return 0
            row = conn.execute(f'SELECT COUNT(*) AS c FROM "{table}"').fetchone()
        return int(row["c"] if row else 0)
