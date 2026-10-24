import pytest

from app import approval, auth, db

SID = "sugg-approval"


def seed(status="pending", guardrail_status="ok", submitted_by=None):
    with db.get_db() as conn:
        conn.execute("DELETE FROM approval_log")
        conn.execute("DELETE FROM suggestion")
        conn.execute(
            "INSERT INTO suggestion (id, event_id, action, impact_low, impact_high,"
            " confidence, gate_level, narrative, generated_by, case_ids, target_price,"
            " margin_at_target, margin_floor, guardrail, guardrail_note, status,"
            " submitted_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                SID, "e1", "follow", 1.0, 2.0, 0.8, "strong", "建议跟价",
                "template:v1", "[]", 89.0, 0.011, 0.15, guardrail_status,
                "测试用", status, submitted_by, "2026-10-24T03:00:00+00:00",
            ),
        )


def test_submit_moves_pending_to_submitted():
    seed()
    with db.get_db() as conn:
        out = approval.submit(conn, SID, "alice", "member", None)
    assert out["status"] == "submitted"
    assert out["submitted_by"] == "alice"


def test_member_cannot_submit_blocked_guardrail():
    seed(guardrail_status="blocked")
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.submit(conn, SID, "alice", "member", None)


def test_admin_can_override_blocked_only_with_note():
    seed(guardrail_status="blocked")
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.submit(conn, SID, "boss", "admin", None)
        out = approval.submit(conn, SID, "boss", "admin", "战略性打击竞品")
    assert out["status"] == "submitted"


def test_cannot_submit_twice():
    seed(status="submitted")
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.submit(conn, SID, "alice", "member", None)


def test_member_cannot_approve():
    seed(status="submitted")
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.approve(conn, SID, "alice", "member", None)


def test_approve_requires_submitted_state():
    seed(status="pending")
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.approve(conn, SID, "boss", "admin", None)


def test_self_approval_blocked_when_auth_enabled(monkeypatch):
    seed(status="submitted", submitted_by="boss")
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.approve(conn, SID, "boss", "admin", None)


def test_full_flow_and_timeline():
    seed()
    with db.get_db() as conn:
        approval.submit(conn, SID, "alice", "member", None)
        approval.approve(conn, SID, "boss", "admin", "同意")
        out = approval.execute(conn, SID, "alice", "member", 89.0, "已改价")
        logs = approval.timeline(conn, SID)
    assert out["status"] == "executed"
    assert out["executed_price"] == 89.0
    assert [x["action"] for x in logs] == ["submit", "approve", "execute"]


def test_execute_requires_approved():
    seed(status="submitted")
    with db.get_db() as conn:
        with pytest.raises(approval.TransitionError):
            approval.execute(conn, SID, "alice", "member", 89.0, None)


def test_reject_from_pending_and_cannot_cancel_after():
    seed()
    with db.get_db() as conn:
        out = approval.reject(conn, SID, "boss", "admin", "不做")
        assert out["status"] == "rejected"
        with pytest.raises(approval.TransitionError):
            approval.cancel(conn, SID, "alice", "member", None)


def test_cancel_from_submitted():
    seed(status="submitted")
    with db.get_db() as conn:
        out = approval.cancel(conn, SID, "alice", "member", "竞品回调了")
    assert out["status"] == "cancelled"


def test_inbox_lists_submitted_only():
    seed(status="submitted")
    with db.get_db() as conn:
        rows = approval.inbox(conn)
    assert any(r["id"] == SID for r in rows)
