"""Agent 记忆：会话级（run 内）与长期级（跨 run 的事实沉淀）。

不引入向量记忆；用关键词 + 时效衰减召回，够用且可解释。
"""

from __future__ import annotations

import json
from typing import Any

from . import db

SESSION = "session"
LONG_TERM = "long_term"


def remember(
    run_id: str | None,
    kind: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    weight: float = 1.0,
) -> str:
    memory_id = db.new_id()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO agent_memory (id, run_id, kind, summary, payload, weight,"
            " created_at, last_used) VALUES (?,?,?,?,?,?,?,?)",
            (
                memory_id, run_id, kind, summary[:500],
                json.dumps(payload or {}, ensure_ascii=False),
                float(weight), db.now_iso(), db.now_iso(),
            ),
        )
    return memory_id


def recall(
    run_id: str | None = None,
    kind: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM agent_memory WHERE 1=1"
    params: list[Any] = []
    if run_id is not None:
        sql += " AND (run_id = ? OR run_id IS NULL)"
        params.append(run_id)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if query:
        sql += " AND LOWER(summary) LIKE ?"
        params.append(f"%{query.lower()[:60]}%")
    sql += " ORDER BY weight DESC, created_at DESC LIMIT ?"
    params.append(limit)
    with db.get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    items = [
        {**dict(row), "payload": json.loads(row["payload"] or "{}")}
        for row in rows
    ]
    if items:
        with db.get_db() as conn:
            conn.execute(
                "UPDATE agent_memory SET last_used = ? WHERE id IN ("
                + ",".join("?" for _ in items) + ")",
                [db.now_iso(), *[item["id"] for item in items]],
            )
    return items


def recall_text(
    run_id: str | None = None, kind: str | None = None,
    query: str | None = None, limit: int = 3,
) -> str:
    items = recall(run_id=run_id, kind=kind, query=query, limit=limit)
    return "\n".join(f"- {item['summary']}" for item in items)


def purge_expired(ttl_seconds: int = 7 * 24 * 3600) -> int:
    """按创建时间做粗粒度清理（ISO 字符串可直接比较）。"""
    from datetime import datetime, timedelta, timezone

    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    ).replace(microsecond=0).isoformat()
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM agent_memory WHERE created_at < ?", (cutoff,)
        ).fetchone()
        conn.execute("DELETE FROM agent_memory WHERE created_at < ?", (cutoff,))
    return int(row["c"] or 0)
