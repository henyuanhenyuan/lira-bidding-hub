from __future__ import annotations

from typing import Any

from . import db

DECISIONS = ("released", "discarded")


def enqueue(
    conn: Any,
    *,
    task_id: str,
    channel: str,
    reason: str,
    target_id: str | None = None,
) -> str:
    review_id = db.new_id()
    conn.execute(
        "INSERT INTO manual_review"
        " (id, task_id, channel, target_id, reason, status, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (review_id, task_id, channel, target_id, reason[:500], "pending",
         db.now_iso()),
    )
    return review_id


def get(conn: Any, review_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM manual_review WHERE id = ?", (review_id,)
    ).fetchone()
    return dict(row) if row else None


def pending(conn: Any, *, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM manual_review WHERE status = 'pending'"
        " ORDER BY created_at, id LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve(
    conn: Any, review_id: str, decision: str, actor: str
) -> str | None:
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    if get(conn, review_id) is None:
        return None
    conn.execute(
        "UPDATE manual_review SET status=?, resolved_at=?, resolved_by=?"
        " WHERE id=?",
        (decision, db.now_iso(), actor, review_id),
    )
    return decision
