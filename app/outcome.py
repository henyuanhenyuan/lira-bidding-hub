from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import cases, db

RESULTS = ("improved", "unchanged", "worse")

RESULT_TEXT = {
    "improved": "销量或毛利改善",
    "unchanged": "无明显变化",
    "worse": "结果变差",
}


def record(
    conn,
    suggestion_id: str,
    result: str,
    note: str | None,
    sales_delta: float | None,
    actor: str,
) -> dict:
    if result not in RESULTS:
        raise ValueError("result must be improved|unchanged|worse")

    sugg = conn.execute(
        "SELECT * FROM suggestion WHERE id = ?", (suggestion_id,)
    ).fetchone()
    if not sugg:
        raise KeyError(suggestion_id)

    conn.execute(
        "INSERT INTO outcome (id, suggestion_id, result, note, sales_delta,"
        " recorded_by, recorded_at) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(suggestion_id) DO UPDATE SET result = excluded.result,"
        " note = excluded.note, sales_delta = excluded.sales_delta,"
        " recorded_by = excluded.recorded_by, recorded_at = excluded.recorded_at",
        (
            db.new_id(), suggestion_id, result, note, sales_delta, actor, db.now_iso(),
        ),
    )

    case_id = None
    if sugg["status"] in ("accepted", "executed", "holdout"):
        # 采纳 + 有结果 → 自动沉淀为案例，供后续检索
        ev = conn.execute(
            "SELECT e.*, t.title AS target_title FROM event e"
            " LEFT JOIN target t ON t.id = e.target_id WHERE e.id = ?",
            (sugg["event_id"],),
        ).fetchone()
        if ev:
            pp = conn.execute(
                "SELECT * FROM price_point WHERE target_id = ? AND ts = ?",
                (ev["target_id"], ev["ts"]),
            ).fetchone()
            band = cases.price_band_of(
                (pp["price_low"] + pp["price_high"]) / 2
            ) if pp else "0-50"
            summary = f"{ev['target_title'] or ev['target_id']}：{ev['note']}"
            outcome_text = f"{RESULT_TEXT[result]}"
            if note:
                outcome_text += f"；{note}"
            case_id = cases.create(
                conn,
                category="自动沉淀",
                event_type=ev["type"],
                price_band=band,
                delta_pct=None,
                summary=summary[:180],
                attribution=sugg["narrative"][:180],
                decision=sugg["action"],
                outcome_7d=outcome_text[:180],
                ts=db.now_iso(),
                case_id=f"auto-{suggestion_id[:12]}",
            )

    return {"suggestion_id": suggestion_id, "result": result, "case_id": case_id}


def get(conn, suggestion_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM outcome WHERE suggestion_id = ?", (suggestion_id,)
    ).fetchone()
    return dict(row) if row else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _observed(
    conn, target_id: str | None, baseline_ts: str | None, due_at: datetime
) -> dict | None:
    if not target_id:
        return None
    rows = conn.execute(
        "SELECT ts, price_low, price_high FROM price_point"
        " WHERE target_id = ? ORDER BY ts",
        (target_id,),
    ).fetchall()
    points = []
    for row in rows:
        parsed = _parse(row["ts"])
        if parsed:
            points.append((parsed, (row["price_low"] + row["price_high"]) / 2, row["ts"]))
    if not points:
        return None
    baseline = _parse(baseline_ts)
    before = None
    if baseline:
        eligible = [item for item in points if item[0] <= baseline]
        before = eligible[-1] if eligible else points[0]
    else:
        before = points[0]
    after = next((item for item in points if item[0] > due_at), points[-1])
    delta = None
    if before[1]:
        delta = round((after[1] - before[1]) / before[1], 4)
    return {
        "baseline_ts": before[2],
        "baseline_price": round(before[1], 2),
        "after_ts": after[2],
        "after_price": round(after[1], 2),
        "delta_pct": delta,
    }


def due_list(conn, days: int = 7, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT s.id, s.event_id, s.action, s.status, s.created_at, s.executed_at,"
        " s.executed_price, e.target_id, e.ts AS event_ts,"
        " t.title AS target_title"
        " FROM suggestion s"
        " LEFT JOIN outcome o ON o.suggestion_id = s.id"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " WHERE s.status IN ('accepted', 'executed', 'holdout') AND o.id IS NULL"
        " ORDER BY COALESCE(s.executed_at, s.created_at)"
    ).fetchall()

    result = []
    for row in rows:
        started = _parse(row["executed_at"] or row["created_at"])
        if not started:
            continue
        due_at = started + timedelta(days=days)
        delta = (now - due_at).total_seconds() / 86400
        result.append(
            {
                **dict(row),
                "due_at": due_at.isoformat(timespec="seconds"),
                "days_overdue": round(delta, 2),
                "due": delta >= 0,
                "observed": _observed(conn, row["target_id"], row["event_ts"], due_at),
            }
        )
    return result


def overdue(conn, days: int = 7) -> list[dict]:
    return [row for row in due_list(conn, days) if row["due"]]
