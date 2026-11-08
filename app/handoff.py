"""多 Agent 之间的结构化交接（handoff）。

只做有界交接：同一 run 内最多 MAX_HANDOFFS 次，超出后走确定性路径。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from . import db

MAX_HANDOFFS = 2


@dataclass
class Handoff:
    source: str
    target: str
    intent: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def record(run_id: str, seq: int, handoff: Handoff, name: str = "") -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO agent_step (id, run_id, seq, kind, name, status, input,"
            " output, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                db.new_id(), run_id, seq, "handoff",
                name or f"{handoff.source}->{handoff.target}", "ok",
                json.dumps(handoff.payload, ensure_ascii=False), handoff.intent,
                0, db.now_iso(),
            ),
        )


def count(run_id: str) -> int:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM agent_step WHERE run_id = ? AND kind = 'handoff'",
            (run_id,),
        ).fetchone()
    return int(row["c"] or 0)


def allowed(run_id: str) -> bool:
    return count(run_id) < MAX_HANDOFFS


def chain(run_id: str) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT name, input, output FROM agent_step"
            " WHERE run_id = ? AND kind = 'handoff' ORDER BY seq",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]
