from app import collect_logs, db


def test_recent_returns_newest_first():
    with db.get_db() as conn:
        collect_logs.record(
            conn, task_id="t1", channel="rpa", account="a", shop="s",
            status_code=200, latency_ms=1200, outcome="done",
        )
        collect_logs.record(
            conn, task_id="t2", channel="api", status_code=429,
            latency_ms=300, outcome="error", error_kind="rate_limited",
        )
        rows = collect_logs.recent(conn)
    assert [r["task_id"] for r in rows] == ["t2", "t1"]


def test_recent_filters_by_channel_and_limit():
    with db.get_db() as conn:
        for i in range(3):
            collect_logs.record(conn, task_id=f"r{i}", channel="rpa", outcome="done")
        collect_logs.record(conn, task_id="api1", channel="api", outcome="done")
        assert len(collect_logs.recent(conn, channel="rpa")) == 3
        assert len(collect_logs.recent(conn, channel="rpa", limit=2)) == 2
        assert collect_logs.recent(conn, channel="api")[0]["task_id"] == "api1"


def test_summary_counts_outcomes_and_errors():
    with db.get_db() as conn:
        collect_logs.record(conn, task_id="a", channel="rpa", outcome="done")
        collect_logs.record(conn, task_id="b", channel="rpa", outcome="error",
                            error_kind="captcha")
        collect_logs.record(conn, task_id="c", channel="rpa", outcome="error",
                            error_kind="captcha")
        summary = collect_logs.summary(conn)
    assert summary["outcomes"]["done"] == 1
    assert summary["outcomes"]["error"] == 2
    assert summary["errors"]["captcha"] == 2
