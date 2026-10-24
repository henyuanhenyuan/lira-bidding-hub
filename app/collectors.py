from __future__ import annotations

import os
from datetime import datetime, timezone

FRESH_SLA_HOURS = float(os.getenv("LIRA_FRESH_SLA_HOURS", "12"))


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _lag_hours(last: datetime | None, now: datetime) -> float | None:
    if last is None:
        return None
    # 采集端时钟可能超前，负滞后按 0 处理
    return round(max(0.0, (now - last).total_seconds() / 3600), 1)


def health(conn, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT collector, COUNT(*) AS c, MAX(ts) AS last_ts"
        " FROM snapshot GROUP BY collector"
    ).fetchall()
    out = []
    for row in rows:
        lag = _lag_hours(_parse_ts(row["last_ts"]), now)
        out.append({
            "collector": row["collector"],
            "snapshots": row["c"],
            "last_ts": row["last_ts"],
            "lag_hours": lag,
            "stale": lag is None or lag > FRESH_SLA_HOURS,
        })
    out.sort(key=lambda x: (x["lag_hours"] is None, -(x["lag_hours"] or 0)))
    return out


def freshness(conn, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    row = conn.execute("SELECT MAX(ts) AS latest FROM snapshot").fetchone()
    latest = row["latest"] if row else None
    lag = _lag_hours(_parse_ts(latest), now)
    return {
        "latest_ts": latest,
        "lag_hours": lag,
        "stale": lag is None or lag > FRESH_SLA_HOURS,
        "sla_hours": FRESH_SLA_HOURS,
    }
