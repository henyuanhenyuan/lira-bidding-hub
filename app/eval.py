from __future__ import annotations

import json
from typing import Any

from . import agent_graph, db, ingest
from .contracts import SnapshotIn

TARGET_PLACEHOLDER = "__TARGET__"


def _snap(ts: str, price: float, tier: int, title: str, complete: bool = True) -> dict:
    observation: dict[str, Any] = {
        "list_price": price,
        "account_tier": "normal",
        "title": title,
    }
    if complete:
        observation["coupons"] = []
        observation["promotions"] = []
        observation["coin"] = {"rate": 0, "cap": 0}
    return {
        "target_id": TARGET_PLACEHOLDER,
        "ts": ts,
        "collector": "eval",
        "source_tier": tier,
        "observation": observation,
    }


GOLDEN_CASES = [
    {
        "name": "L3 降价（三方源）",
        "expected_action": "adjust_coupon",
        "expected_event_type": "price_drop",
        "notes": "299 → 199，-33%，L3 状态应给投券对冲",
        "payload": {
            "snapshots": [
                _snap("2026-10-20T02:00:00+08:00", 299, 1, "评测竞品A"),
                _snap("2026-10-21T02:00:00+08:00", 199, 1, "评测竞品A"),
            ]
        },
    },
    {
        "name": "L2 降价",
        "expected_action": "hold",
        "expected_event_type": "price_drop",
        "notes": "199 → 175，-12%，未到 L3，先观察",
        "payload": {
            "snapshots": [
                _snap("2026-10-20T02:00:00+08:00", 199, 1, "评测竞品B"),
                _snap("2026-10-21T02:00:00+08:00", 175, 1, "评测竞品B"),
            ]
        },
    },
    {
        "name": "提价",
        "expected_action": "hold",
        "expected_event_type": "price_rise",
        "notes": "199 → 229，+15%，提价通常先观察",
        "payload": {
            "snapshots": [
                _snap("2026-10-20T02:00:00+08:00", 199, 1, "评测竞品C"),
                _snap("2026-10-21T02:00:00+08:00", 229, 1, "评测竞品C"),
            ]
        },
    },
    {
        "name": "价格带击穿",
        "expected_action": "follow",
        "expected_event_type": "band_breach",
        "notes": "我方 100，竞品 99 → 89，击穿价格带",
        "payload": {
            "my_price": 100,
            "snapshots": [
                _snap("2026-10-20T02:00:00+08:00", 99, 1, "评测竞品D"),
                _snap("2026-10-21T02:00:00+08:00", 89, 1, "评测竞品D"),
            ],
        },
    },
    {
        "name": "低置信观察",
        "expected_action": "no_action",
        "expected_event_type": "price_drop",
        "notes": "tier 4 且缺券/活动/金币字段，置信度不足只能观察",
        "payload": {
            "snapshots": [
                _snap("2026-10-20T02:00:00+08:00", 299, 4, "评测竞品E", complete=False),
                _snap("2026-10-21T02:00:00+08:00", 260, 4, "评测竞品E", complete=False),
            ]
        },
    },
]


def ensure_cases(conn) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM eval_case").fetchone()["c"]
    if count:
        return
    for case in GOLDEN_CASES:
        conn.execute(
            "INSERT INTO eval_case (id, name, payload, expected_action,"
            " expected_event_type, notes, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                db.new_id(), case["name"],
                json.dumps(case["payload"], ensure_ascii=False),
                case["expected_action"], case["expected_event_type"],
                case["notes"], db.now_iso(),
            ),
        )


def list_cases(conn) -> list[dict[str, Any]]:
    ensure_cases(conn)
    rows = conn.execute(
        "SELECT id, name, expected_action, expected_event_type, notes, created_at"
        " FROM eval_case ORDER BY created_at, name"
    ).fetchall()
    return [dict(row) for row in rows]


def _marks(items: list[str]) -> str:
    return ", ".join("?" for _ in items)


def _cleanup(run_key: str, target_ids: list[str]) -> None:
    if not target_ids:
        return
    marks = _marks(target_ids)
    with db.get_db() as conn:
        event_rows = conn.execute(
            f"SELECT id FROM event WHERE target_id IN ({marks})", target_ids
        ).fetchall()
        event_ids = [row["id"] for row in event_rows]
        if event_ids:
            event_marks = _marks(event_ids)
            suggestion_rows = conn.execute(
                f"SELECT id FROM suggestion WHERE event_id IN ({event_marks})",
                event_ids,
            ).fetchall()
            suggestion_ids = [row["id"] for row in suggestion_rows]
            if suggestion_ids:
                suggestion_marks = _marks(suggestion_ids)
                conn.execute(
                    f"DELETE FROM outcome WHERE suggestion_id IN ({suggestion_marks})",
                    suggestion_ids,
                )
                conn.execute(
                    f"DELETE FROM approval_log WHERE suggestion_id IN ({suggestion_marks})",
                    suggestion_ids,
                )
                conn.execute(
                    f"DELETE FROM action_log WHERE suggestion_id IN ({suggestion_marks})",
                    suggestion_ids,
                )
            conn.execute(
                f"DELETE FROM suggestion WHERE event_id IN ({event_marks})",
                event_ids,
            )
            run_rows = conn.execute(
                f"SELECT id FROM agent_run WHERE event_id IN ({event_marks})",
                event_ids,
            ).fetchall()
            run_ids = [row["id"] for row in run_rows]
            if run_ids:
                run_marks = _marks(run_ids)
                conn.execute(
                    f"DELETE FROM agent_step WHERE run_id IN ({run_marks})", run_ids
                )
            conn.execute(
                f"DELETE FROM agent_run WHERE event_id IN ({event_marks})", event_ids
            )
            conn.execute(f"DELETE FROM event WHERE id IN ({event_marks})", event_ids)
        conn.execute(
            f"DELETE FROM price_point WHERE target_id IN ({marks})", target_ids
        )
        conn.execute(f"DELETE FROM snapshot WHERE target_id IN ({marks})", target_ids)
        conn.execute(f"DELETE FROM target WHERE id IN ({marks})", target_ids)
        conn.execute("DELETE FROM ingest_log WHERE source = ?", (f"eval:{run_key}",))


def run(limit: int | None = None) -> dict[str, Any]:
    with db.get_db() as conn:
        ensure_cases(conn)
        cases = conn.execute(
            "SELECT * FROM eval_case ORDER BY created_at, name"
        ).fetchall()
    if limit:
        cases = cases[:limit]

    run_key = db.new_id()[:8]
    target_ids = [f"eval-{run_key}-{index}" for index in range(len(cases))]
    results: list[dict[str, Any]] = []

    for index, case in enumerate(cases):
        target_id = target_ids[index]
        payload = json.loads(case["payload"])
        snapshots = [
            SnapshotIn(**{**item, "target_id": target_id})
            for item in payload.get("snapshots", [])
        ]

        try:
            with db.get_db() as conn:
                ingest.ingest(
                    conn, snapshots[:1], source=f"eval:{run_key}"
                )
                if payload.get("my_price") is not None:
                    conn.execute(
                        "UPDATE target SET my_price = ? WHERE id = ?",
                        (payload["my_price"], target_id),
                    )
            with db.get_db() as conn:
                ingest.ingest(
                    conn, snapshots[1:], source=f"eval:{run_key}"
                )
        except Exception as exc:
            results.append(
                {
                    "case": case["name"], "passed": False, "error": f"ingest: {exc}",
                    "expected_action": case["expected_action"],
                }
            )
            continue

        with db.get_db() as conn:
            events = conn.execute(
                "SELECT id, type, severity FROM event WHERE target_id = ?"
                " AND suppressed = 0 ORDER BY ts DESC",
                (target_id,),
            ).fetchall()
        wanted = case["expected_event_type"]
        event = next((row for row in events if row["type"] == wanted), None)
        if event is None and events:
            event = events[0]
        if event is None:
            results.append(
                {
                    "case": case["name"], "passed": False, "error": "no event",
                    "expected_action": case["expected_action"],
                }
            )
            continue

        error = None
        suggestion = None
        try:
            suggestion = agent_graph.run_for_event(
                event["id"], trigger=f"eval:{run_key}"
            )
        except Exception as exc:
            error = str(exc)

        with db.get_db() as conn:
            event_row = conn.execute(
                "SELECT evidence FROM event WHERE id = ?", (event["id"],)
            ).fetchone()
            latency = None
            if suggestion and suggestion.get("agent_run_id"):
                run_row = conn.execute(
                    "SELECT latency_ms FROM agent_run WHERE id = ?",
                    (suggestion["agent_run_id"],),
                ).fetchone()
                latency = run_row["latency_ms"] if run_row else None
        evidence = db.loads(event_row["evidence"], []) if event_row else []

        actual_action = suggestion["action"] if suggestion else None
        passed = bool(
            suggestion
            and actual_action == case["expected_action"]
            and evidence
        )
        results.append(
            {
                "case": case["name"],
                "passed": passed,
                "event_type": event["type"],
                "expected_event_type": wanted,
                "expected_action": case["expected_action"],
                "actual_action": actual_action,
                "evidence_count": len(evidence),
                "guardrail": suggestion.get("guardrail") if suggestion else None,
                "latency_ms": latency,
                "error": error,
            }
        )

    _cleanup(run_key, target_ids)

    passed = sum(1 for item in results if item["passed"])
    accuracy = round(passed / len(results), 3) if results else 0.0
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO eval_run (id, run_key, total, passed, accuracy, results,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            (
                db.new_id(), run_key, len(results), passed, accuracy,
                json.dumps(results, ensure_ascii=False), db.now_iso(),
            ),
        )
    return {
        "run_key": run_key,
        "total": len(results),
        "passed": passed,
        "accuracy": accuracy,
        "results": results,
    }
