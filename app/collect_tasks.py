from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import db

CHANNELS = ("api", "rpa", "manual")
STATUSES = ("pending", "running", "done", "failed")


def _iso(offset_s: float = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).isoformat(
        timespec="seconds"
    )


def create(
    conn: Any,
    *,
    target_id: str,
    channel: str,
    priority: int = 0,
    max_attempts: int = 3,
    next_run_at: str | None = None,
) -> str:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel}")
    task_id = db.new_id()
    now = db.now_iso()
    conn.execute(
        "INSERT INTO collect_task"
        " (id, target_id, channel, status, priority, attempts, max_attempts,"
        "  next_run_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,0,?,?,?,?)",
        (task_id, target_id, channel, "pending", priority, max_attempts,
         next_run_at, now, now),
    )
    return task_id


def get(conn: Any, task_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM collect_task WHERE id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row else None


def claim(conn: Any, *, channel: str, limit: int = 1) -> list[dict]:
    """把到期的 pending 任务转成 running。并发下靠 status 条件更新保证不重复领取。"""
    now = db.now_iso()
    rows = conn.execute(
        "SELECT id FROM collect_task"
        " WHERE channel = ? AND status = 'pending'"
        "   AND (next_run_at IS NULL OR next_run_at <= ?)"
        " ORDER BY priority DESC, next_run_at, created_at LIMIT ?",
        (channel, now, limit),
    ).fetchall()
    claimed: list[dict] = []
    for row in rows:
        task_id = row["id"]
        cur = conn.execute(
            "UPDATE collect_task SET status='running', attempts = attempts + 1,"
            " locked_at = ?, updated_at = ? WHERE id = ? AND status = 'pending'",
            (now, now, task_id),
        )
        if cur.rowcount == 0:
            continue
        claimed.append(get(conn, task_id))
    return claimed


def complete(conn: Any, task_id: str) -> None:
    conn.execute(
        "UPDATE collect_task SET status='done', locked_at=NULL, last_error=NULL,"
        " updated_at=? WHERE id=?",
        (db.now_iso(), task_id),
    )


def fail(
    conn: Any, task_id: str, error: str, *, retry_delay_s: float = 300
) -> str | None:
    row = get(conn, task_id)
    if row is None:
        return None
    if row["attempts"] >= row["max_attempts"]:
        status, next_run_at = "failed", None
    else:
        status, next_run_at = "pending", _iso(retry_delay_s)
    conn.execute(
        "UPDATE collect_task SET status=?, next_run_at=?, locked_at=NULL,"
        " last_error=?, updated_at=? WHERE id=?",
        (status, next_run_at, error[:500], db.now_iso(), task_id),
    )
    return status


def release_stale(conn: Any, *, older_than_s: float = 900) -> int:
    """worker 崩溃后，running 会永久卡住；超过阈值放回 pending。"""
    threshold = _iso(-older_than_s)
    cur = conn.execute(
        "UPDATE collect_task SET status='pending', locked_at=NULL, updated_at=?"
        " WHERE status='running' AND locked_at IS NOT NULL AND locked_at <= ?",
        (db.now_iso(), threshold),
    )
    return cur.rowcount or 0


def counts(conn: Any) -> dict[str, int]:
    out = {status: 0 for status in STATUSES}
    for row in conn.execute(
        "SELECT status, COUNT(*) AS c FROM collect_task GROUP BY status"
    ).fetchall():
        out[row["status"]] = row["c"]
    return out
