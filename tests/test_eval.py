from fastapi.testclient import TestClient

from app import db
from app import eval as eval_store
from app.main import app

client = TestClient(app)


def test_golden_cases_all_pass_and_cleanup():
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, title, active)"
            " VALUES ('keep-me', 'taobao', '保留目标', 1)"
        )

    result = eval_store.run()

    assert result["total"] >= 5
    assert result["passed"] == result["total"], result["results"]
    assert result["accuracy"] == 1.0

    with db.get_db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM eval_run"
        ).fetchone()["c"] == 1
        assert conn.execute(
            "SELECT accuracy FROM eval_run"
        ).fetchone()["accuracy"] == 1.0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM target WHERE id LIKE 'eval-%'"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM agent_run WHERE trigger LIKE 'eval:%'"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM target WHERE id = 'keep-me'"
        ).fetchone()["c"] == 1


def test_eval_reports_mismatch():
    with db.get_db() as conn:
        eval_store.ensure_cases(conn)
        conn.execute(
            "UPDATE eval_case SET expected_action = 'follow' WHERE name = 'L2 降价'"
        )

    result = eval_store.run()

    assert result["passed"] == result["total"] - 1
    failed = [item for item in result["results"] if not item["passed"]]
    assert failed and failed[0]["case"] == "L2 降价"
    assert failed[0]["actual_action"] != failed[0]["expected_action"]


def test_eval_api():
    cases = client.get("/api/eval/cases").json()
    assert len(cases) >= 5

    result = client.post("/api/eval/run").json()
    assert result["total"] == len(cases)
    assert "results" in result
