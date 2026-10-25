from __future__ import annotations

from typing import Any

from . import db


def record(
    conn: Any,
    *,
    channel: str,
    outcome: str,
    task_id: str | None = None,
    account: str | None = None,
    shop: str | None = None,
    status_code: int | None = None,
    latency_ms: int | None = None,
    error_kind: str | None = None,
    detail: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO collect_log"
        " (ts, task_id, channel, account, shop, status_code, latency_ms,"
        "  outcome, error_kind, detail)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (db.now_iso(), task_id, channel, account, shop, status_code,
         latency_ms, outcome, error_kind, (detail or "")[:500]),
    )


def recent(
    conn: Any, *, limit: int = 100, channel: str | None = None
) -> list[dict]:
    sql = "SELECT * FROM collect_log"
    params: list[Any] = []
    if channel:
        sql += " WHERE channel = ?"
        params.append(channel)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def summary(conn: Any, *, hours: int = 24) -> dict:
    outcomes: dict[str, int] = {}
    errors: dict[str, int] = {}
    since = f"-{max(1, min(hours, 720))} hours"
    for row in conn.execute(
        "SELECT outcome, COUNT(*) AS c FROM collect_log"
        " WHERE datetime(ts) >= datetime('now', ?) GROUP BY outcome",
        (since,),
    ).fetchall():
        outcomes[row["outcome"]] = row["c"]
    for row in conn.execute(
        "SELECT error_kind, COUNT(*) AS c FROM collect_log"
        " WHERE error_kind IS NOT NULL AND datetime(ts) >= datetime('now', ?)"
        " GROUP BY error_kind",
        (since,),
    ).fetchall():
        errors[row["error_kind"]] = row["c"]
    return {"hours": hours, "outcomes": outcomes, "errors": errors}
