from fastapi.testclient import TestClient

from app import collect_logs, db, review_queue
from app.main import app

client = TestClient(app)


def test_collect_logs_endpoint():
    with db.get_db() as conn:
        collect_logs.record(
            conn, task_id="t1", channel="rpa", outcome="done", latency_ms=100
        )
    response = client.get("/api/collect/logs")
    assert response.status_code == 200
    assert response.json()["logs"][0]["task_id"] == "t1"


def test_collect_logs_filters_channel():
    with db.get_db() as conn:
        collect_logs.record(conn, task_id="r1", channel="rpa", outcome="done")
        collect_logs.record(conn, task_id="a1", channel="api", outcome="done")
    body = client.get("/api/collect/logs?channel=api").json()
    assert [row["task_id"] for row in body["logs"]] == ["a1"]


def test_collect_summary_endpoint():
    with db.get_db() as conn:
        collect_logs.record(conn, task_id="t1", channel="rpa", outcome="error",
                            error_kind="captcha")
    body = client.get("/api/collect/summary?hours=24").json()
    assert body["outcomes"]["error"] == 1
    assert body["errors"]["captcha"] == 1


def test_review_queue_list_and_resolve():
    with db.get_db() as conn:
        review_id = review_queue.enqueue(
            conn, task_id="t1", channel="rpa", reason="captcha"
        )
    listing = client.get("/api/collect/reviews").json()
    assert listing["reviews"][0]["id"] == review_id

    resolved = client.post(
        f"/api/collect/reviews/{review_id}/resolve?decision=released"
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "released"
    assert client.get("/api/collect/reviews").json()["reviews"] == []


def test_review_bad_decision_returns_400():
    with db.get_db() as conn:
        review_id = review_queue.enqueue(
            conn, task_id="t1", channel="rpa", reason="captcha"
        )
    response = client.post(
        f"/api/collect/reviews/{review_id}/resolve?decision=nope"
    )
    assert response.status_code == 400


def test_health_reports_vector_index():
    body = client.get("/api/health").json()
    assert "vector_index" in body
    assert body["vector_index"]["cases"] >= 0
    assert isinstance(body["vector_index"]["stale"], bool)


def test_collect_task_crud():
    created = client.post(
        "/api/collect/tasks",
        json={"target_id": "t1", "channel": "rpa", "interval_s": 900},
    )
    assert created.status_code == 200, created.text
    task = created.json()
    assert task["interval_s"] == 900

    listing = client.get("/api/collect/tasks").json()
    assert any(item["id"] == task["id"] for item in listing["tasks"])

    cancelled = client.delete(f"/api/collect/tasks/{task['id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_collect_task_bad_channel_returns_400():
    response = client.post(
        "/api/collect/tasks", json={"target_id": "t1", "channel": "selenium"}
    )
    assert response.status_code == 400


def test_review_missing_returns_404():
    response = client.post("/api/collect/reviews/nope/resolve?decision=released")
    assert response.status_code == 404
