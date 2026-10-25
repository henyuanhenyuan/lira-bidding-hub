import pytest

from app import db, review_queue


def test_enqueue_and_list_pending():
    with db.get_db() as conn:
        review_id = review_queue.enqueue(
            conn, task_id="task-1", channel="rpa", target_id="sku-1",
            reason="circuit open",
        )
        rows = review_queue.pending(conn)
    assert [r["id"] for r in rows] == [review_id]
    assert rows[0]["status"] == "pending"


def test_resolve_removes_from_pending():
    with db.get_db() as conn:
        review_id = review_queue.enqueue(
            conn, task_id="task-1", channel="rpa", reason="captcha"
        )
        assert review_queue.resolve(conn, review_id, "released", "admin") == "released"
        assert review_queue.pending(conn) == []
        row = review_queue.get(conn, review_id)
    assert row["status"] == "released"
    assert row["resolved_by"] == "admin"


def test_unknown_decision_rejected():
    with db.get_db() as conn:
        review_id = review_queue.enqueue(
            conn, task_id="task-1", channel="rpa", reason="captcha"
        )
        with pytest.raises(ValueError):
            review_queue.resolve(conn, review_id, "whatever", "admin")


def test_resolve_missing_returns_none():
    with db.get_db() as conn:
        assert review_queue.resolve(conn, "nope", "discarded", "admin") is None
