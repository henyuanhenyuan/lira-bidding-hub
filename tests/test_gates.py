from fastapi.testclient import TestClient

from app import db, gates, metrics
from app.main import app

client = TestClient(app)


def _eval_row(accuracy: float) -> None:
    with db.get_db() as conn:
        conn.execute("DELETE FROM eval_run")
        conn.execute(
            "INSERT INTO eval_run (id, run_key, total, passed, accuracy, results,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            (
                db.new_id(), "gate-test", 5, round(5 * accuracy), accuracy,
                "[]", db.now_iso(),
            ),
        )


def _event_id() -> str:
    client.post(
        "/v1/ingest/snapshots",
        json={
            "snapshots": [
                {
                    "target_id": "t1", "ts": "2026-10-23T02:00:00+08:00",
                    "collector": "eval", "source_tier": 1,
                    "observation": {"list_price": 299, "title": "竞品A"},
                },
                {
                    "target_id": "t1", "ts": "2026-10-24T02:00:00+08:00",
                    "collector": "eval", "source_tier": 1,
                    "observation": {"list_price": 199, "title": "竞品A"},
                },
            ]
        },
    )
    return client.get("/api/events").json()[0]["id"]


def test_gate_requires_eval_record(monkeypatch):
    monkeypatch.setattr(gates, "MIN_ACCURACY", 0.8)
    with db.get_db() as conn:
        state = gates.status(conn)
    assert state["ok"] is False
    assert any("评测" in reason for reason in state["reasons"])


def test_gate_passes_and_fails_by_accuracy(monkeypatch):
    monkeypatch.setattr(gates, "MIN_ACCURACY", 0.8)
    _eval_row(0.9)
    with db.get_db() as conn:
        assert gates.status(conn)["ok"] is True

    _eval_row(0.5)
    with db.get_db() as conn:
        state = gates.status(conn)
    assert state["ok"] is False
    assert state["latest_eval"]["accuracy"] == 0.5


def test_enforcement_blocks_analyze(monkeypatch):
    monkeypatch.setattr(gates, "ENFORCE", True)
    monkeypatch.setattr(gates, "MIN_ACCURACY", 0.8)
    event_id = _event_id()

    _eval_row(0.4)
    blocked = client.post(f"/api/events/{event_id}/analyze")
    assert blocked.status_code == 423
    assert "上线门禁" in blocked.json()["detail"]

    _eval_row(0.95)
    allowed = client.post(f"/api/events/{event_id}/analyze")
    assert allowed.status_code == 200, allowed.text


def test_gate_api_shape(monkeypatch):
    monkeypatch.setattr(gates, "MIN_ACCURACY", 0.8)
    _eval_row(1.0)
    body = client.get("/api/gates").json()
    assert body["ok"] is True
    assert body["thresholds"]["min_accuracy"] == 0.8
    assert "usage" in body


def test_gate_warns_on_high_fallback(monkeypatch):
    _eval_row(1.0)
    metrics.record("attribution", ok=False, fallback=True)
    metrics.record("attribution", ok=False, fallback=True)
    with db.get_db() as conn:
        state = gates.status(conn)
    assert any("回退率" in warning for warning in state["warnings"])
