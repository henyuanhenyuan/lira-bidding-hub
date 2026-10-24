from __future__ import annotations

import json

from . import auth, db, guardrail

# 状态：pending → submitted → approved → executed
#              ↘ rejected        ↘ cancelled
APPROVER_ROLES = ("admin", "manager")
MEMBER_ROLES = ("admin", "manager", "member")

ACTION_TEXT = {
    "submit": "提交执行",
    "approve": "批准",
    "reject": "驳回",
    "execute": "标记已执行",
    "cancel": "取消",
}


class TransitionError(Exception):
    pass


def _log(conn, sid: str, actor: str, action: str, frm: str, to: str, note: str | None) -> None:
    conn.execute(
        "INSERT INTO approval_log (id, suggestion_id, actor, action, from_status,"
        " to_status, note, at, seq) VALUES (?,?,?,?,?,?,?,?,"
        " (SELECT COALESCE(MAX(seq), 0) + 1 FROM approval_log))",
        (db.new_id(), sid, actor, action, frm, to, note, db.now_iso()),
    )


def _load(conn, sid: str):
    row = conn.execute("SELECT * FROM suggestion WHERE id = ?", (sid,)).fetchone()
    if not row:
        raise KeyError(sid)
    return row


def _require(role: str, allowed: tuple[str, ...], action: str) -> None:
    if role not in allowed:
        raise TransitionError(f"当前角色 {role} 无权执行「{ACTION_TEXT[action]}」")


def _guardrail_allows(sugg, actor_role: str, note: str | None) -> None:
    state = sugg["guardrail"] or "unknown"
    if state in ("ok", "warning"):
        return
    if state == "blocked":
        if actor_role not in APPROVER_ROLES or not note:
            raise TransitionError(
                "毛利护栏已拦截：需管理员填写理由后强制放行"
            )
        return
    # unknown：没有成本数据，任何执行都要审批人确认
    if actor_role not in APPROVER_ROLES:
        raise TransitionError("未设置成本价，需管理员确认后才能推进")


def submit(conn, sid: str, actor: str, role: str, note: str | None = None) -> dict:
    _require(role, MEMBER_ROLES, "submit")
    sugg = _load(conn, sid)
    if sugg["status"] != "pending":
        raise TransitionError(f"当前状态 {sugg['status']} 不可提交")
    _guardrail_allows(sugg, role, note)

    conn.execute(
        "UPDATE suggestion SET status = 'submitted', submitted_by = ? WHERE id = ?",
        (actor, sid),
    )
    _log(conn, sid, actor, "submit", "pending", "submitted", note)
    return _snapshot(conn, sid)


def approve(conn, sid: str, actor: str, role: str, note: str | None = None) -> dict:
    _require(role, APPROVER_ROLES, "approve")
    sugg = _load(conn, sid)
    if sugg["status"] != "submitted":
        raise TransitionError(f"当前状态 {sugg['status']} 不可审批")
    if auth.AUTH_ENABLED and sugg["submitted_by"] == actor:
        raise TransitionError("不能审批自己提交的建议")

    conn.execute(
        "UPDATE suggestion SET status = 'approved', approved_by = ? WHERE id = ?",
        (actor, sid),
    )
    _log(conn, sid, actor, "approve", "submitted", "approved", note)
    return _snapshot(conn, sid)


def reject(conn, sid: str, actor: str, role: str, note: str | None = None) -> dict:
    _require(role, APPROVER_ROLES, "reject")
    sugg = _load(conn, sid)
    if sugg["status"] not in ("submitted", "pending"):
        raise TransitionError(f"当前状态 {sugg['status']} 不可驳回")

    conn.execute("UPDATE suggestion SET status = 'rejected' WHERE id = ?", (sid,))
    _log(conn, sid, actor, "reject", sugg["status"], "rejected", note)
    return _snapshot(conn, sid)


def execute(
    conn, sid: str, actor: str, role: str,
    executed_price: float | None, note: str | None = None,
) -> dict:
    _require(role, MEMBER_ROLES, "execute")
    sugg = _load(conn, sid)
    if sugg["status"] != "approved":
        raise TransitionError(f"当前状态 {sugg['status']} 不可执行")

    if executed_price is not None:
        # 执行价同样要过护栏，防止审批后私自压价
        product_cost = None
        row = conn.execute(
            "SELECT p.cost FROM target t JOIN my_product p ON p.sku = t.my_sku"
            " JOIN event e ON e.target_id = t.id WHERE e.id = ?",
            (sugg["event_id"],),
        ).fetchone()
        if row:
            product_cost = row["cost"]
        check = guardrail.evaluate(
            executed_price, product_cost, sugg["margin_floor"]
        )
        if check.status == "blocked" and role not in APPROVER_ROLES:
            raise TransitionError(f"执行价触碰护栏：{check.note}")

    conn.execute(
        "UPDATE suggestion SET status = 'executed', executed_price = ?,"
        " executed_at = ? WHERE id = ?",
        (executed_price, db.now_iso(), sid),
    )
    _log(conn, sid, actor, "execute", "approved", "executed", note)
    return _snapshot(conn, sid)


def rollback(
    conn, sid: str, actor: str, role: str, note: str | None = None
) -> dict:
    _require(role, MEMBER_ROLES, "rollback")
    sugg = _load(conn, sid)
    if sugg["status"] != "executed":
        raise TransitionError(f"当前状态 {sugg['status']} 不可回滚")
    conn.execute(
        "UPDATE suggestion SET status = 'approved', executed_price = NULL,"
        " executed_at = NULL, execution_id = NULL WHERE id = ?",
        (sid,),
    )
    _log(conn, sid, actor, "rollback", "executed", "approved", note)
    return _snapshot(conn, sid)


def cancel(conn, sid: str, actor: str, role: str, note: str | None = None) -> dict:
    _require(role, MEMBER_ROLES, "cancel")
    sugg = _load(conn, sid)
    if sugg["status"] in ("executed", "rejected", "cancelled"):
        raise TransitionError(f"当前状态 {sugg['status']} 不可取消")
    conn.execute("UPDATE suggestion SET status = 'cancelled' WHERE id = ?", (sid,))
    _log(conn, sid, actor, "cancel", sugg["status"], "cancelled", note)
    return _snapshot(conn, sid)


def _snapshot(conn, sid: str) -> dict:
    row = conn.execute("SELECT * FROM suggestion WHERE id = ?", (sid,)).fetchone()
    return {**dict(row), "case_ids": db.loads(row["case_ids"], [])}


def timeline(conn, sid: str) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT * FROM approval_log WHERE suggestion_id = ? ORDER BY at, seq",
            (sid,),
        ).fetchall()
    ]


def inbox(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT s.*, e.target_id, e.type AS event_type, t.title AS target_title"
        " FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " WHERE s.status = 'submitted' ORDER BY s.created_at"
    ).fetchall()
    return [{**dict(r), "case_ids": db.loads(r["case_ids"], [])} for r in rows]
