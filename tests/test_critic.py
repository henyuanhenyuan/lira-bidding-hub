from fastapi.testclient import TestClient

from app import agent
from app.main import app

client = TestClient(app)


def _ingest_event():
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
    return client.get("/api/events").json()[0]


def test_critic_reject_falls_back_to_template(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LLM_CRITIC", "on")
    monkeypatch.setattr(
        agent,
        "critic_review",
        lambda facts, analysis, allowed: {
            "verdict": "reject", "issues": ["narrative 数字与事实不一致"],
        },
    )
    event = _ingest_event()
    suggestion = client.post(f"/api/events/{event['id']}/analyze").json()

    assert suggestion["generated_by"] == "template:v1"
    run = client.get(f"/api/agent/runs/{suggestion['agent_run_id']}").json()
    assert run["status"] == "succeeded"
    kinds = [step["kind"] for step in run["steps"]]
    assert "critic" in kinds
    assert "fallback" in kinds


def test_critic_approve_keeps_analysis(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LLM_CRITIC", "on")
    monkeypatch.setattr(
        agent,
        "critic_review",
        lambda facts, analysis, allowed: {"verdict": "approve", "issues": []},
    )
    event = _ingest_event()
    suggestion = client.post(f"/api/events/{event['id']}/analyze").json()

    run = client.get(f"/api/agent/runs/{suggestion['agent_run_id']}").json()
    kinds = [step["kind"] for step in run["steps"]]
    assert "critic" in kinds
    assert "fallback" not in kinds
