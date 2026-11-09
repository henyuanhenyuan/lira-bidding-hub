"""自主竞价：Agent 自动执行，只有异常才升级人工。

分流规则是确定性的，模型不参与。每次决策都写入 bid_ledger，形成可追溯流水。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from . import approval, db, executor, settings_store, stream

AUTO = "auto"
EXCEPTION = "exception"
MANUAL = "manual"

_PASS_THROUGH = ("hold", "no_action")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "on", "yes"}


def config() -> dict[str, Any]:
    data = settings_store.load()
    enabled = _env_bool("LIRA_AUTOPILOT", bool(data.get("autopilot_enabled", True)))
    return {
        "enabled": enabled,
        "strategy": str(data.get("autopilot_strategy") or "follow"),
        "undercut_pct": float(data.get("autopilot_undercut_pct") or 0.02),
        "max_delta_pct": float(
            os.getenv("LIRA_AUTO_MAX_DELTA", data.get("autopilot_max_delta_pct") or 0.15)
        ),
        "min_confidence": float(
            os.getenv("LIRA_AUTO_MIN_CONF", data.get("autopilot_min_confidence") or 0.80)
        ),
    }


@dataclass
class Decision:
    mode: str
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "reasons": list(self.reasons)}


def _row(conn, suggestion_id: str):
    return conn.execute(
        "SELECT s.*, e.target_id, e.type AS event_type, e.severity,"
        " t.title AS target_title, t.region, t.my_price, t.pricing_strategy,"
        " p.cost, p.margin_floor AS product_floor"
        " FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " LEFT JOIN my_product p ON p.sku = t.my_sku"
        " WHERE s.id = ?",
        (suggestion_id,),
    ).fetchone()


def assess(sugg) -> Decision:
    """决定这条建议是自动执行还是进异常队列。"""
    cfg = config()
    if not cfg["enabled"]:
        return Decision(MANUAL, ["自动驾驶已关闭"])

    action = sugg["action"]
    if sugg["status"] != "pending":
        return Decision(MANUAL, [f"状态 {sugg['status']} 不参与自动分流"])
    if sugg.get("holdout"):
        return Decision(EXCEPTION, ["该目标在留出对照实验中，不自动改价"])
    if action in _PASS_THROUGH:
        return Decision(AUTO, ["无需改价，自动归档"])

    reasons: list[str] = []
    guard = sugg["guardrail"] or "unknown"
    if guard == "blocked":
        reasons.append(f"毛利护栏拦截：{sugg['guardrail_note'] or '触碰底线'}")
    elif guard == "unknown":
        reasons.append("缺少成本数据，无法校验毛利")
    elif guard == "warning":
        reasons.append(f"毛利接近下限：{sugg['guardrail_note'] or ''}".strip())

    if (sugg["confidence"] or 0) < cfg["min_confidence"]:
        reasons.append(
            f"置信度 {sugg['confidence']:.0%} 低于 {cfg['min_confidence']:.0%}"
        )

    target = sugg["target_price"]
    my_price = sugg["my_price"]
    if action not in _PASS_THROUGH and target is None:
        reasons.append("没有可执行的目标价")
    if target is not None and my_price:
        delta = abs(float(target) - float(my_price)) / float(my_price)
        if delta > cfg["max_delta_pct"]:
            reasons.append(
                f"单次调价 {delta:+.1%} 超过 {cfg['max_delta_pct']:.0%} 阈值"
            )

    if sugg.get("exception") and sugg.get("exception_reason"):
        reasons.append(str(sugg["exception_reason"]))

    return Decision(EXCEPTION if reasons else AUTO, reasons)


def _write_ledger(
    conn,
    *,
    sugg,
    mode: str,
    status: str,
    to_price: float | None,
    execution_id: str | None = None,
    reason: str | None = None,
) -> str:
    ledger_id = db.new_id()
    my_price = sugg["my_price"]
    target = to_price if to_price is not None else sugg["target_price"]
    delta = None
    if target is not None and my_price:
        delta = round((float(target) - float(my_price)) / float(my_price), 4)
    conn.execute(
        "INSERT INTO bid_ledger (id, ts, target_id, region, action, mode, status,"
        " from_price, to_price, delta_pct, margin_at_target, guardrail,"
        " suggestion_id, execution_id, run_id, strategy, reason, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ledger_id, db.now_iso(), sugg["target_id"], sugg["region"] or "全国",
            sugg["action"], mode, status, my_price, target, delta,
            sugg["margin_at_target"], sugg["guardrail"], sugg["id"], execution_id,
            sugg["agent_run_id"], sugg["pricing_strategy"] or config()["strategy"],
            (reason or "")[:500], db.now_iso(),
        ),
    )
    return ledger_id


def _publish(sugg, decision: Decision, status: str, ledger_id: str) -> None:
    stream.publish(
        "autopilot",
        {
            "suggestion_id": sugg["id"],
            "target_id": sugg["target_id"],
            "target_title": sugg["target_title"],
            "region": sugg["region"],
            "action": sugg["action"],
            "mode": decision.mode,
            "status": status,
            "reasons": decision.reasons,
            "ledger_id": ledger_id,
        },
    )


def apply(suggestion_id: str) -> dict[str, Any]:
    """在建议落库后立即分流；返回决策与流水。"""
    with db.get_db() as conn:
        sugg = _row(conn, suggestion_id)
        if sugg is None:
            raise KeyError(suggestion_id)
        if sugg["status"] != "pending" or sugg["decided_at"]:
            decision = Decision(sugg["mode"] or MANUAL, ["已处理"])
            return {"decision": decision.as_dict(), "suggestion_id": suggestion_id}

        decision = assess(sugg)
        meta = json.dumps(decision.as_dict(), ensure_ascii=False)

        if decision.mode == MANUAL:
            conn.execute(
                "UPDATE suggestion SET mode='manual', decided_at=? WHERE id=?",
                (db.now_iso(), suggestion_id),
            )
            return {"decision": decision.as_dict(), "suggestion_id": suggestion_id}

        if decision.mode == EXCEPTION:
            reason = "；".join(decision.reasons)
            conn.execute(
                "UPDATE suggestion SET mode='auto', exception=1, exception_reason=?,"
                " decided_at=?, decision_meta=? WHERE id=?",
                (reason[:500], db.now_iso(), meta, suggestion_id),
            )
            ledger_id = _write_ledger(
                conn, sugg=sugg, mode=EXCEPTION, status="exception",
                to_price=sugg["target_price"], reason=reason,
            )
            sugg = {**dict(sugg), "exception": 1}
            _publish(sugg, decision, "exception", ledger_id)
            return {
                "decision": decision.as_dict(), "ledger_id": ledger_id,
                "suggestion_id": suggestion_id,
            }

        conn.execute(
            "UPDATE suggestion SET mode='auto', exception=0, decided_at=?,"
            " decision_meta=? WHERE id=?",
            (db.now_iso(), meta, suggestion_id),
        )

        if sugg["action"] in _PASS_THROUGH:
            conn.execute(
                "UPDATE suggestion SET status='auto_closed' WHERE id=?",
                (suggestion_id,),
            )
            ledger_id = _write_ledger(
                conn, sugg=sugg, mode=AUTO, status="held",
                to_price=sugg["my_price"], reason="无需改价",
            )
            _publish(sugg, decision, "held", ledger_id)
            return {
                "decision": decision.as_dict(), "ledger_id": ledger_id,
                "suggestion_id": suggestion_id,
            }

        # 自动改价：先落 approval_log，再调用统一执行器
        conn.execute(
            "UPDATE suggestion SET status='approved', approved_by='agent:autopilot'"
            " WHERE id=?",
            (suggestion_id,),
        )
        approval._log(
            conn, suggestion_id, "agent:autopilot", "approve", "pending", "approved",
            "自动驾驶：护栏与置信度校验通过",
        )

    try:
        result = executor.run(
            suggestion_id, actor="agent:autopilot", role="admin",
            executed_price=sugg["target_price"],
            note="自动驾驶：策略 " + (sugg["pricing_strategy"] or config()["strategy"]),
        )
    except Exception as exc:
        with db.get_db() as conn:
            reason = f"自动执行失败：{exc}"
            conn.execute(
                "UPDATE suggestion SET status='pending', exception=1,"
                " exception_reason=? WHERE id=?",
                (reason[:500], suggestion_id),
            )
            ledger_id = _write_ledger(
                conn, sugg=sugg, mode=EXCEPTION, status="failed",
                to_price=sugg["target_price"], reason=reason,
            )
        _publish(sugg, Decision(EXCEPTION, [reason]), "failed", ledger_id)
        return {"decision": Decision(EXCEPTION, [reason]).as_dict(),
                "ledger_id": ledger_id, "suggestion_id": suggestion_id}

    with db.get_db() as conn:
        conn.execute(
            "UPDATE suggestion SET status='executed', executed_price=?, executed_at=?,"
            " execution_id=? WHERE id=?",
            (sugg["target_price"], db.now_iso(), result.get("id"), suggestion_id),
        )
        approval._log(
            conn, suggestion_id, "agent:autopilot", "execute", "approved", "executed",
            "自动驾驶：执行完成",
        )
        ledger_id = _write_ledger(
            conn, sugg=sugg, mode=AUTO, status="executed",
            to_price=sugg["target_price"], execution_id=result.get("id"),
            reason="护栏与置信度校验通过",
        )
    _publish(sugg, decision, "executed", ledger_id)
    return {
        "decision": decision.as_dict(), "ledger_id": ledger_id,
        "execution_id": result.get("id"), "suggestion_id": suggestion_id,
    }


def resolve_exception(
    conn, suggestion_id: str, actor: str, role: str,
    *, approve: bool, note: str | None = None,
    executed_price: float | None = None,
) -> dict[str, Any]:
    """人工处理异常：批准后走同一执行器，驳回则关闭。"""
    if role not in ("admin", "manager"):
        raise approval.TransitionError("异常确认需要管理员或主管角色")
    row = _row(conn, suggestion_id)
    if row is None:
        raise KeyError(suggestion_id)
    if not row["exception"] or row["status"] not in ("pending", "submitted"):
        raise approval.TransitionError(f"当前状态 {row['status']} 不是待确认异常")

    if not approve:
        conn.execute(
            "UPDATE suggestion SET status='rejected', exception=0"
            " WHERE id=?",
            (suggestion_id,),
        )
        approval._log(
            conn, suggestion_id, actor, "reject", row["status"], "rejected", note
        )
        ledger_id = _write_ledger(
            conn, sugg=row, mode=EXCEPTION, status="rejected",
            to_price=None, reason=f"人工驳回：{note or '无说明'}",
        )
        return {"suggestion_id": suggestion_id, "status": "rejected",
                "ledger_id": ledger_id}

    price = executed_price if executed_price is not None else row["target_price"]
    conn.execute(
        "UPDATE suggestion SET status='approved', exception=0, approved_by=?"
        " WHERE id=?",
        (actor, suggestion_id),
    )
    approval._log(
        conn, suggestion_id, actor, "approve", row["status"], "approved",
        note or "人工确认异常后放行",
    )

    # 执行器会另开连接读取建议，先把 approved 状态提交
    conn.commit()

    result = executor.run(
        suggestion_id, actor=actor, role=role, executed_price=price,
        note=note or "人工确认异常后放行",
    )
    with db.get_db() as conn:
        conn.execute(
            "UPDATE suggestion SET status='executed', executed_price=?, executed_at=?,"
            " execution_id=? WHERE id=?",
            (price, db.now_iso(), result.get("id"), suggestion_id),
        )
        ledger_id = _write_ledger(
            conn, sugg=row, mode=EXCEPTION, status="confirmed",
            to_price=price, execution_id=result.get("id"),
            reason=f"人工确认：{note or '无说明'}",
        )
    return {
        "suggestion_id": suggestion_id, "status": "executed",
        "execution_id": result.get("id"), "ledger_id": ledger_id,
    }


def exceptions(conn, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT s.*, e.target_id, e.type AS event_type, t.title AS target_title,"
        " t.region, t.my_price FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " WHERE s.exception = 1 AND s.status IN ('pending','submitted')"
        " ORDER BY s.created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [{**dict(r), "decision_meta": db.loads(r["decision_meta"], {})} for r in rows]


def ledger(
    conn, *, region: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    if region:
        rows = conn.execute(
            "SELECT * FROM bid_ledger WHERE region = ? ORDER BY created_at DESC LIMIT ?",
            (region, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bid_ledger ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def regions(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT region, COUNT(*) AS targets,"
        " COALESCE(AVG(my_price), 0) AS avg_price"
        " FROM target WHERE active = 1 GROUP BY region ORDER BY region"
    ).fetchall()
    return [dict(r) for r in rows]


def status(conn) -> dict[str, Any]:
    cfg = config()
    counts = conn.execute(
        "SELECT"
        " SUM(CASE WHEN mode='auto' AND status='executed' THEN 1 ELSE 0 END) AS auto_executed,"
        " SUM(CASE WHEN mode='auto' AND status='auto_closed' THEN 1 ELSE 0 END) AS auto_held,"
        " SUM(CASE WHEN exception=1 AND status IN ('pending','submitted') THEN 1 ELSE 0 END) AS exceptions,"
        " SUM(CASE WHEN mode='manual' AND status IN ('pending','submitted') THEN 1 ELSE 0 END) AS manual_pending"
        " FROM suggestion"
    ).fetchone()
    last = conn.execute(
        "SELECT * FROM bid_ledger ORDER BY created_at DESC LIMIT 8"
    ).fetchall()
    return {
        "config": cfg,
        "counts": {k: int(v or 0) for k, v in dict(counts).items()},
        "recent": [dict(r) for r in last],
    }
