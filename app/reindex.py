from __future__ import annotations

from typing import Any

from . import cases, db, docs, embeddings, vectorstore


def reindex(conn: Any) -> dict[str, int]:
    """按文本重建 Qdrant 向量。旧库 BLOB 已删除，且 provider 可能不同，重新嵌入更可靠。"""
    grouped: dict[str, list[vectorstore.Point]] = {}

    case_rows = conn.execute(
        'SELECT id, category, event_type, summary, attribution FROM "case"'
    ).fetchall()
    for row in case_rows:
        text = f"{row['summary']}\n{row['attribution']}\n{row['category']} {row['event_type']}"
        vector, provider = embeddings.embed(text)
        grouped.setdefault(cases.collection_name(provider, len(vector)), []).append(
            vectorstore.Point(
                row["id"], vector,
                {"category": row["category"], "event_type": row["event_type"]},
            )
        )

    chunk_rows = conn.execute(
        "SELECT id, doc_id, chunk_no, content, parent_id FROM doc_chunk"
        " WHERE level = 'child'"
    ).fetchall()
    for row in chunk_rows:
        vector, provider = embeddings.embed(row["content"])
        grouped.setdefault(docs.collection_name(provider, len(vector)), []).append(
            vectorstore.Point(
                row["id"], vector,
                {
                    "doc_id": row["doc_id"],
                    "chunk_no": row["chunk_no"],
                    "parent_id": row["parent_id"] or "",
                },
            )
        )

    store = vectorstore.QdrantVectorStore()
    for name, points in grouped.items():
        store.upsert(name, points)
    return {"cases": len(case_rows), "doc_chunks": len(chunk_rows)}
