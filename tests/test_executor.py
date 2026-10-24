from fastapi.testclient import TestClient

from app import executor
from app.main import app

client = TestClient(app)


def _approved_suggestion():
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
    event = client.get("/api/events").json()[0]
    suggestion = client.post(f"/api/events/{event['id']}/analyze").json()
    client.post(f"/api/suggestions/{suggestion['id']}/submit", json={})
    client.post(f"/api/suggestions/{suggestion['id']}/approve", json={})
    return suggestion


def test_preview_and_execute_off_mode(monkeypatch):
    monkeypatch.setattr(executor, "MODE", "off")
    suggestion = _approved_suggestion()

    preview = client.get(
        f"/api/suggestions/{suggestion['id']}/execution-preview"
    ).json()
    assert preview["plan"]["to_price"] == 199.0
    assert preview["plan"]["guardrail"] in ("ok", "warning", "blocked", "unknown")

    response = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 210},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "executed"
    assert body["executed_price"] == 210.0
    assert body["executed_at"]
    assert body["execution"]["mode"] == "off"
    assert body["execution"]["status"] == "recorded"

    history = client.get(
        f"/api/suggestions/{suggestion['id']}/executions"
    ).json()
    assert len(history) == 1


def test_execute_is_idempotent(monkeypatch):
    monkeypatch.setattr(executor, "MODE", "off")
    suggestion = _approved_suggestion()

    first = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 210},
    ).json()
    second = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 210},
    )
    assert second.status_code == 200
    assert second.json()["execution"]["id"] == first["execution"]["id"]
    assert second.json()["status"] == "executed"


def test_rollback_returns_suggestion_to_approved(monkeypatch):
    monkeypatch.setattr(executor, "MODE", "off")
    suggestion = _approved_suggestion()
    executed = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 210},
    ).json()

    response = client.post(
        f"/api/executions/{executed['execution']['id']}/rollback"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rolled_back"

    detail = client.get(f"/api/suggestions/{suggestion['id']}").json()
    assert detail["status"] == "approved"
    assert detail["executed_at"] is None
    assert detail["execution_id"] is None


def test_retry_after_rollback_creates_new_attempt(monkeypatch):
    monkeypatch.setattr(executor, "MODE", "off")
    suggestion = _approved_suggestion()
    first = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 210},
    ).json()
    client.post(f"/api/executions/{first['execution']['id']}/rollback")

    second = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 210},
    )
    assert second.status_code == 200, second.text
    assert second.json()["execution"]["id"] != first["execution"]["id"]

    history = client.get(
        f"/api/suggestions/{suggestion['id']}/executions"
    ).json()
    assert len(history) == 2


def test_webhook_mode_posts_idempotent_request(monkeypatch):
    monkeypatch.setattr(executor, "MODE", "webhook")
    monkeypatch.setattr(executor, "URL", "https://example.invalid/execute")
    monkeypatch.setattr(executor, "TOKEN", "secret")
    calls: dict = {}

    class FakeResponse:
        status_code = 200
        content = b'{"external_id":"ext-1"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"external_id": "ext-1"}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(executor.httpx, "post", fake_post)
    suggestion = _approved_suggestion()

    body = client.post(
        f"/api/suggestions/{suggestion['id']}/execute",
        json={"executed_price": 200},
    ).json()

    assert body["execution"]["mode"] == "webhook"
    assert body["execution"]["status"] == "succeeded"
    assert body["execution"]["external_id"] == "ext-1"
    assert calls["url"] == "https://example.invalid/execute"
    assert calls["headers"]["Authorization"] == "Bearer secret"
    assert calls["json"]["idempotency_key"]
    assert calls["json"]["to_price"] == 200.0
