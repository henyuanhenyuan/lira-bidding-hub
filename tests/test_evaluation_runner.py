import json

from app import db
from app.evaluation import datasets, runner


def test_runner_smoke_writes_metrics_and_tier():
    result = runner.run(tier="smoke", limit=4, write_artifact=False)

    assert result["tier"] == "smoke"
    assert result["total"] == 4
    metrics = result["metrics"]
    for key in (
        "action_accuracy", "evidence_closure_rate", "trace_completion_rate",
        "by_segment", "by_difficulty",
    ):
        assert key in metrics

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT tier, metrics FROM eval_run WHERE run_key = ?",
            (result["run_key"],),
        ).fetchone()
    assert row["tier"] == "smoke"
    assert json.loads(row["metrics"])["total"] == 4


def test_runner_enriches_segment_on_results():
    result = runner.run(tier="smoke", limit=2, write_artifact=False)
    for item in result["results"]:
        assert item["segment"] != "unknown"
        assert item["difficulty"] == "easy"


def test_badcases_are_archived():
    with db.get_db() as conn:
        runner._archive(
            conn, "run-x",
            [{
                "case": "坏例A", "segment": "price_event", "difficulty": "easy",
                "passed": False, "expected_action": "hold",
                "actual_action": "follow", "evidence_count": 1, "trace_ok": True,
            }],
        )
    rows = runner.list_badcases("run-x")
    assert rows and rows[0]["case_name"] == "坏例A"
    assert "动作不符" in rows[0]["reason"]


def test_list_runs_returns_metrics():
    runner.run(tier="smoke", limit=1, write_artifact=False)
    runs = runner.list_runs(5)
    assert runs and runs[0]["metrics"]["total"] == 1


def test_datasets_seed_only_selected_cases():
    selected = datasets.select(datasets.load(), "smoke")[:3]
    with db.get_db() as conn:
        datasets.seed(conn, selected)
    with db.get_db() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM eval_case").fetchone()["c"]
    assert count == 3
