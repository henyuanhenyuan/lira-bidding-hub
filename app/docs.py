from __future__ import annotations

from typing import Any

from llama_index.core.node_parser import (
    HierarchicalNodeParser,
    SentenceSplitter,
    get_leaf_nodes,
)
from llama_index.core.schema import Document as LIDocument
from llama_index.core.schema import NodeRelationship

from . import db, embeddings, vectorstore

MAX_CHARS = 500
OVERLAP = 80
PARENT_CHARS = 1200
CHILD_CHARS = 300
RRF_K = 60


def _normalize(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def split_text(
    text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP
) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    splitter = SentenceSplitter(chunk_size=max_chars, chunk_overlap=overlap)
    return [chunk.strip() for chunk in splitter.split_text(normalized) if chunk.strip()]


def split_hierarchy(
    text: str,
    parent_chars: int = PARENT_CHARS,
    child_chars: int = CHILD_CHARS,
    overlap: int = 60,
) -> list[dict[str, Any]]:
    """父块按小节、子块按句群。子块用于召回，父块用于喂模型。"""
    normalized = _normalize(text)
    if not normalized:
        return []
    parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=[parent_chars, child_chars], chunk_overlap=overlap
    )
    nodes = parser.get_nodes_from_documents([LIDocument(text=normalized)])
    leaf_ids = {node.node_id for node in get_leaf_nodes(nodes)}
    local_ids = {node.node_id: db.new_id() for node in nodes}

    out: list[dict[str, Any]] = []
    for node in nodes:
        parent = node.relationships.get(NodeRelationship.PARENT)
        out.append(
            {
                "id": local_ids[node.node_id],
                "text": node.get_content().strip(),
                "level": "child" if node.node_id in leaf_ids else "parent",
                "parent_id": local_ids.get(parent.node_id) if parent else None,
            }
        )
    return out


def collection_name(provider: str, dim: int) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in provider)
    return f"doc_chunks_{safe}_{dim}"


def create_doc(
    conn,
    *,
    title: str,
    content: str,
    source: str | None = None,
    category: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    nodes = split_hierarchy(content)
    if not nodes:
        raise ValueError("文档内容为空")

    doc_id = db.new_id()
    conn.execute(
        "INSERT INTO doc (id, title, source, category, version, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (doc_id, title.strip(), source, category, version, db.now_iso()),
    )

    batches: dict[str, list[vectorstore.Point]] = {}
    now = db.now_iso()
    for index, node in enumerate(nodes):
        vector, provider = embeddings.embed(node["text"])
        conn.execute(
            "INSERT INTO doc_chunk (id, doc_id, chunk_no, content, embed_provider,"
            " dim, created_at, parent_id, level) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                node["id"], doc_id, index, node["text"], provider, len(vector),
                now, node["parent_id"], node["level"],
            ),
        )
        if node["level"] != "child":
            continue
        key = collection_name(provider, len(vector))
        batches.setdefault(key, []).append(
            vectorstore.Point(
                node["id"],
                vector,
                {
                    "doc_id": doc_id,
                    "chunk_no": index,
                    "parent_id": node["parent_id"] or "",
                },
            )
        )

    store = vectorstore.PgVectorStore()
    for name, points in batches.items():
        store.upsert(name, points)
    return get_doc(conn, doc_id)


def get_doc(conn, doc_id: str) -> dict[str, Any] | None:
    doc = conn.execute("SELECT * FROM doc WHERE id = ?", (doc_id,)).fetchone()
    if not doc:
        return None
    chunks = conn.execute(
        "SELECT id, chunk_no, content, level, parent_id FROM doc_chunk"
        " WHERE doc_id = ? ORDER BY chunk_no",
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
        "SELECT c.id, c.doc_id, c.chunk_no, c.content, c.level, c.parent_id,"
        " d.title AS doc_title"
        " FROM doc_chunk c JOIN doc d ON d.id = c.doc_id WHERE c.id = ?",
        (chunk_id,),
    ).fetchone()
    return dict(row) if row else None


def search_docs(conn, query: str, limit: int = 3) -> list[dict[str, Any]]:
    text = (query or "").strip()
    if not text:
        return []
    rows = conn.execute(
        "SELECT c.id, c.doc_id, c.chunk_no, c.content, c.parent_id, c.level,"
        " d.title AS doc_title"
        " FROM doc_chunk c JOIN doc d ON d.id = c.doc_id WHERE c.level = 'child'"
    ).fetchall()
    if not rows:
        return []
    by_id = {row["id"]: row for row in rows}

    qvec, provider = embeddings.embed(text)
    hits = vectorstore.PgVectorStore().search(
        collection_name(provider, len(qvec)), qvec, top_k=20
    )
    vector_rank = [hit.id for hit in hits if hit.id in by_id]

    keyword_rank: list[str] = []
    try:
        keyword_rows = conn.execute(
            "SELECT id FROM doc_chunk WHERE level = 'child' AND content LIKE ?"
            " LIMIT 20",
            (f"%{text[:60]}%",),
        ).fetchall()
        keyword_rank = [row["id"] for row in keyword_rows if row["id"] in by_id]
    except Exception:
        keyword_rank = []

    fused: dict[str, float] = {}
    for rank, chunk_id in enumerate(vector_rank):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, chunk_id in enumerate(keyword_rank):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

    if not fused:
        ordered = list(by_id.values())[:limit]
    else:
        ordered = [
            by_id[chunk_id]
            for chunk_id in sorted(fused, key=lambda key: -fused[key])[:limit]
        ]

    parent_ids = {row["parent_id"] for row in ordered if row["parent_id"]}
    parents: dict[str, str] = {}
    if parent_ids:
        placeholders = ",".join("?" for _ in parent_ids)
        for row in conn.execute(
            f"SELECT id, content FROM doc_chunk WHERE id IN ({placeholders})",
            tuple(parent_ids),
        ).fetchall():
            parents[row["id"]] = row["content"]

    return [
        {
            "id": row["id"],
            "doc_id": row["doc_id"],
            "doc_title": row["doc_title"],
            "chunk_no": row["chunk_no"],
            "content": row["content"],
            "parent_content": parents.get(row["parent_id"], row["content"]),
            "score": round(fused.get(row["id"], 0.0), 4),
        }
        for row in ordered
    ]


def delete_doc(conn, doc_id: str) -> None:
    conn.execute("DELETE FROM doc_chunk WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM doc WHERE id = ?", (doc_id,))
