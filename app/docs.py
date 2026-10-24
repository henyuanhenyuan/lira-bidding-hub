from __future__ import annotations

import re
import struct
from typing import Any

import numpy as np

from . import db, embeddings

MAX_CHARS = 500
OVERLAP = 80
RRF_K = 60


def split_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    """按段落切分，超长段落再按窗口切，窗口间保留 overlap 字符。"""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    raw_blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
    blocks: list[str] = []
    pending = ""
    for block in raw_blocks:
        # 标题或短行与下一段合并，避免出现只有标题的切片
        if block.startswith("#") or len(block) < 40:
            pending = f"{pending}\n\n{block}".strip() if pending else block
            continue
        blocks.append(f"{pending}\n\n{block}".strip() if pending else block)
        pending = ""
    if pending:
        blocks.append(pending)

    chunks: list[str] = []
    current = ""
    step = max(1, max_chars - overlap)
    for block in blocks:
        if len(block) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(block):
                piece = block[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
                start += step
        else:
            candidate = f"{current}\n\n{block}".strip() if current else block
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = block
    if current:
        chunks.append(current)
    return chunks


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def create_doc(
    conn,
    *,
    title: str,
    content: str,
    source: str | None = None,
    category: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    chunks = split_text(content)
    if not chunks:
        raise ValueError("文档内容为空")

    prepared: list[tuple[int, str, str, list[float]]] = []
    for index, chunk in enumerate(chunks):
        vector, provider = embeddings.embed(chunk)
        prepared.append((index, chunk, provider, vector))

    doc_id = db.new_id()
    conn.execute(
        "INSERT INTO doc (id, title, source, category, version, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (doc_id, title.strip(), source, category, version, db.now_iso()),
    )
    for index, chunk, provider, vector in prepared:
        conn.execute(
            "INSERT INTO doc_chunk (id, doc_id, chunk_no, content, embed_provider,"
            " dim, embedding, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                db.new_id(), doc_id, index, chunk, provider, len(vector),
                _pack(vector), db.now_iso(),
            ),
        )
    return get_doc(conn, doc_id)


def get_doc(conn, doc_id: str) -> dict[str, Any] | None:
    doc = conn.execute("SELECT * FROM doc WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        return None
    chunks = conn.execute(
        "SELECT id, chunk_no, content FROM doc_chunk WHERE doc_id = ?"
        " ORDER BY chunk_no",
        (doc_id,),
    ).fetchall()
    return {**dict(doc), "chunks": [dict(row) for row in chunks], "chunk_count": len(chunks)}


def list_docs(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT d.id, d.title, d.source, d.category, d.version, d.created_at,"
        " COUNT(c.id) AS chunk_count"
        " FROM doc d LEFT JOIN doc_chunk c ON c.doc_id = d.id"
        " GROUP BY d.id, d.title, d.source, d.category, d.version, d.created_at"
        " ORDER BY d.created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_chunk(conn, chunk_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT c.id, c.doc_id, c.chunk_no, c.content, d.title AS doc_title"
        " FROM doc_chunk c JOIN doc d ON d.id = c.doc_id WHERE c.id = ?",
        (chunk_id,),
    ).fetchone()
    return dict(row) if row else None


def search_docs(conn, query: str, limit: int = 3) -> list[dict[str, Any]]:
    text = (query or "").strip()
    if not text:
        return []
    rows = conn.execute(
        "SELECT c.id, c.doc_id, c.chunk_no, c.content, c.embed_provider, c.dim,"
        " c.embedding, d.title AS doc_title"
        " FROM doc_chunk c JOIN doc d ON d.id = c.doc_id"
    ).fetchall()
    if not rows:
        return []

    qvec, provider = embeddings.embed(text)
    same = [row for row in rows if row["embed_provider"] == provider and row["dim"] == len(qvec)]
    vector_rank: list[str] = []
    if same:
        matrix = np.vstack([_unpack(row["embedding"]) for row in same])
        query_vec = np.array(qvec, dtype=np.float32)
        scores = matrix @ query_vec
        order = np.argsort(-scores)[:20]
        vector_rank = [same[int(i)]["id"] for i in order]

    keyword_rank: list[str] = []
    try:
        keyword_rows = conn.execute(
            "SELECT id FROM doc_chunk WHERE content LIKE ? LIMIT 20",
            (f"%{text[:60]}%",),
        ).fetchall()
        keyword_rank = [row["id"] for row in keyword_rows]
    except Exception:
        keyword_rank = []

    fused: dict[str, float] = {}
    for rank, chunk_id in enumerate(vector_rank):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, chunk_id in enumerate(keyword_rank):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

    by_id = {row["id"]: row for row in rows}
    if not fused:
        ordered = rows[:limit]
    else:
        ordered = [by_id[chunk_id] for chunk_id in sorted(fused, key=lambda key: -fused[key])[:limit]]

    return [
        {
            "id": row["id"],
            "doc_id": row["doc_id"],
            "doc_title": row["doc_title"],
            "chunk_no": row["chunk_no"],
            "content": row["content"],
            "score": round(fused.get(row["id"], 0.0), 4),
        }
        for row in ordered
    ]
