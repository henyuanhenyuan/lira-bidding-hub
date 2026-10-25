import fakeredis

from app import collect_logs, collect_tasks, collector, db, review_queue
from app.channels.base import DispatchResult
from app.contracts import SnapshotIn


class FakeAdapter:
    channel = "rpa"

    def __init__(self, result):
        self.result = result
        self.seen: list[str] = []

    def dispatch(self, task):
        self.seen.append(task["id"])
        return self.result


def _client():
    return fakeredis.FakeRedis(decode_responses=True)


def _snapshot():
    return SnapshotIn(
        target_id="t1",
        ts="2026-10-25T00:00:00+00:00",
        collector="api",
        source_tier=1,
        observation={"list_price": 99.0},
    )


def test_pending_dispatch_marks_done_and_logs():
    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="rpa")
    adapter = FakeAdapter(DispatchResult("pending", external_ref="t1.json", detail="已下发"))
    summary = collector.dispatch_due(
        "rpa", adapter=adapter, rl_client=_client(), risk_client=_client()
    )
    assert summary["pending"] == 1
    with db.get_db() as conn:
        assert collect_tasks.get(conn, task_id)["status"] == "done"
        assert collect_logs.recent(conn)[0]["outcome"] == "pending"


def test_done_dispatch_ingests_observations():
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="t1", channel="api")
    adapter = FakeAdapter(DispatchResult("done", observations=[_snapshot()]))
    summary = collector.dispatch_due(
        "api", adapter=adapter, rl_client=_client(), risk_client=_client()
    )
    assert summary["done"] == 1
    with db.get_db() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM snapshot").fetchone()
    assert row["c"] == 1


def test_skipped_dispatch_reschedules():
    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="api")
    adapter = FakeAdapter(DispatchResult("skipped", detail="未配置"))
    summary = collector.dispatch_due(
        "api", adapter=adapter, rl_client=_client(), risk_client=_client()
    )
    assert summary["skipped"] == 1
    with db.get_db() as conn:
        row = collect_tasks.get(conn, task_id)
    assert row["status"] == "pending"
    assert row["next_run_at"] is not None


def test_recurring_task_is_rescheduled():
    with db.get_db() as conn:
        task_id = collect_tasks.create(
            conn, target_id="t1", channel="rpa", interval_s=600
        )
    adapter = FakeAdapter(DispatchResult("pending", external_ref="t1.json"))
    collector.dispatch_due(
        "rpa", adapter=adapter, rl_client=_client(), risk_client=_client()
    )
    with db.get_db() as conn:
        row = collect_tasks.get(conn, task_id)
    assert row["status"] == "pending"
    assert row["next_run_at"] is not None


def test_dispatch_error_opens_circuit(monkeypatch):
    from app import risk

    class Boom:
        channel = "rpa"

        def dispatch(self, task):
            raise RuntimeError("请输入验证码")

    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="t1", channel="rpa")
    client = _client()
    monkeypatch.setattr(collector, "RISK_THRESHOLD", 1)
    summary = collector.dispatch_due(
        "rpa", adapter=Boom(), rl_client=_client(), risk_client=client
    )
    assert summary["error"] == 1
    assert risk.state("rpa", "default", "default", client=client) == "open"
    with db.get_db() as conn:
        assert len(review_queue.pending(conn)) == 1


def test_recover_stale_returns_task_to_pending():
    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="rpa")
        collect_tasks.claim(conn, channel="rpa")
    assert collector.recover_stale(older_than_s=-1) == 1
    with db.get_db() as conn:
        assert collect_tasks.get(conn, task_id)["status"] == "pending"


def test_rate_limit_backpressure_does_not_exhaust_retries():
    client = _client()
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="warmup", channel="rpa")
    collector.dispatch_due(
        "rpa", adapter=FakeAdapter(DispatchResult("pending")),
        rl_client=client, risk_client=_client(), rate=0.1, capacity=1, now=1000.0,
    )
    with db.get_db() as conn:
        task_id = collect_tasks.create(
            conn, target_id="t1", channel="rpa", max_attempts=1
        )
    for _ in range(3):
        collector.dispatch_due(
            "rpa", adapter=FakeAdapter(DispatchResult("pending")),
            rl_client=client, risk_client=_client(),
            rate=0.1, capacity=1, now=1000.0,
        )
    with db.get_db() as conn:
        row = collect_tasks.get(conn, task_id)
    assert row["status"] == "pending"
    assert row["attempts"] == 0


def test_open_circuit_blocks_and_enqueues_review():
    from app import risk

    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="rpa")
    client = _client()
    risk.record_failure(
        "rpa", "default", "default", kind="captcha",
        threshold=1, cooldown_s=600, client=client, now=1000.0,
    )
    adapter = FakeAdapter(DispatchResult("pending"))
    summary = collector.dispatch_due(
        "rpa", adapter=adapter, rl_client=_client(), risk_client=client, now=1000.0
    )
    assert summary["blocked"] == 1
    assert adapter.seen == []
    with db.get_db() as conn:
        assert collect_tasks.get(conn, task_id)["status"] == "pending"
        assert len(review_queue.pending(conn)) == 1


def test_rate_limited_reschedules_without_dispatch():
    client = _client()
    with db.get_db() as conn:
        collect_tasks.create(conn, target_id="warmup", channel="rpa")
    collector.dispatch_due(
        "rpa", adapter=FakeAdapter(DispatchResult("pending")),
        rl_client=client, risk_client=_client(), rate=0.1, capacity=1, now=1000.0,
    )
    with db.get_db() as conn:
        task_id = collect_tasks.create(conn, target_id="t1", channel="rpa")
    summary = collector.dispatch_due(
        "rpa", adapter=FakeAdapter(DispatchResult("pending")),
        rl_client=client, risk_client=_client(), rate=0.1, capacity=1, now=1000.0,
    )
    assert summary["blocked"] == 1
    with db.get_db() as conn:
        assert collect_tasks.get(conn, task_id)["status"] == "pending"
