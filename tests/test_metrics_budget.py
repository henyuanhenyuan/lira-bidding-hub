from app import db, metrics


def test_record_attaches_run_id_and_cost(monkeypatch):
    monkeypatch.setattr(metrics, "COST_PER_1K_TOKENS", 2.0)
    token = metrics.set_run_id("run-x")
    try:
        metrics.record(
            "attribution", model="qwen", prompt_tokens=100, completion_tokens=50
        )
    finally:
        metrics.reset_run_id(token)

    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM model_call").fetchone()
    assert row["run_id"] == "run-x"
    assert row["prompt_tokens"] == 100
    assert row["completion_tokens"] == 50
    assert row["cost"] == 0.3


def test_budget_exceeded(monkeypatch):
    monkeypatch.setattr(metrics, "DAILY_TOKEN_BUDGET", 100)
    assert metrics.budget_exceeded() is False
    metrics.record("attribution", prompt_tokens=80, completion_tokens=30)
    assert metrics.budget_exceeded() is True


def test_budget_unlimited(monkeypatch):
    monkeypatch.setattr(metrics, "DAILY_TOKEN_BUDGET", 0)
    metrics.record("attribution", prompt_tokens=10_000, completion_tokens=10_000)
    assert metrics.budget_exceeded() is False


def test_summary_includes_tokens_and_cost(monkeypatch):
    monkeypatch.setattr(metrics, "COST_PER_1K_TOKENS", 1.0)
    metrics.record("attribution", prompt_tokens=200, completion_tokens=100)
    with db.get_db() as conn:
        summary = metrics.summary(conn, 24)
    assert summary["tokens"] == 300
    assert summary["cost"] == 0.3
    assert summary["prompt_tokens"] == 200
