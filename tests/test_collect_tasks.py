from datetime import datetime, timedelta, timezone

from app import collect_tasks, db


def _iso(offset_s: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).isoformat(timespec="seconds")


def test_create_and_claim():
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="t1", channel="rpa")
        claimed = collect_tasks.claim(conn, channel="rpa")
    assert len(claimed) == 1
    assert claimed[0]["target_id"] == "t1"
    assert claimed[0]["status"] == "running"
    assert claimed[0]["attempts"] == 1


def test_claim_skips_not_due():
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="later", channel="rpa", next_run_at=_iso(3600))
        assert collect_tasks.claim(conn, channel="rpa") == []
        collect_tasks.create(conn, target_id="now", channel="rpa", next_run_at=_iso(-1))
        assert [r["target_id"] for r in collect_tasks.claim(conn, channel="rpa")] == ["now"]


def test_claim_is_channel_scoped_and_priority_ordered():
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="low", channel="rpa", priority=0)
        collect_tasks.create(conn, target_id="high", channel="rpa", priority=10)
        collect_tasks.create(conn, target_id="api1", channel="api")
        claimed = collect_tasks.claim(conn, channel="rpa", limit=1)
    assert claimed[0]["target_id"] == "high"


def test_fail_retries_then_gives_up():
    with db.get_db() as conn:
        task_id = collect_tasks.create(
            conn, target_id="t1", channel="rpa", max_attempts=2
        )
        collect_tasks.claim(conn, channel="rpa")
        assert collect_tasks.fail(conn, task_id, "boom", retry_delay_s=0) == "pending"
        collect_tasks.claim(conn, channel="rpa")
        assert collect_tasks.fail(conn, task_id, "boom again", retry_delay_s=0) == "failed"
        assert "boom again" in collect_tasks.get(conn, task_id)["last_error"]


def test_complete_marks_done():
    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="manual")
        collect_tasks.claim(conn, channel="manual")
        collect_tasks.complete(conn, task_id)
        assert collect_tasks.get(conn, task_id)["status"] == "done"


def test_stale_running_is_released():
    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="rpa")
        collect_tasks.claim(conn, channel="rpa")
        assert collect_tasks.release_stale(conn, older_than_s=-1) == 1
        assert collect_tasks.get(conn, task_id)["status"] == "pending"


def test_unknown_channel_rejected():
    with db.get_db() as conn:
        try:
            collect_tasks.create(conn, target_id="t1", channel="selenium")
        except ValueError as exc:
            assert "selenium" in str(exc)
        else:
            raise AssertionError("unknown channel accepted")


def test_counts_by_status():
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="t1", channel="rpa")
        collect_tasks.create(conn, target_id="t2", channel="api")
        counts = collect_tasks.counts(conn)
    assert counts["pending"] == 2
    assert counts["done"] == 0
