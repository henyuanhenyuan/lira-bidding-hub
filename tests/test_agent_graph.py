from fastapi.testclient import TestClient

from app import agent
from app.main import app

client = TestClient(app)
D1 = "2026-10-23T02:17:00+08:00"
D2 = "2026-10-24T02:17:00+08:00"


def _payload():
    return {
        "snapshots": [
            {
                "target_id": "t1", "ts": D1, "collector": "yd-v1", "source_tier": 3,
                "observation": {"list_price": 299, "title": "竞品A·洗护套装"},
            },
            {
                "target_id": "t1", "ts": D2, "collector": "yd-v1", "source_tier": 3,
                "observation": {"list_price": 199, "title": "竞品A·洗护套装"},
            },
        ]
    }


def _ingest_event():
    client.post("/v1/ingest/snapshots", json=_payload())
    return client.get("/api/events").json()[0]


def test_graph_creates_suggestion_and_trace():
    event = _ingest_event()
    suggestion = client.post(f"/api/events/{event['id']}/analyze").json()

    assert suggestion["agent_run_id"]
    assert suggestion["status"] == "pending"

    run = client.get(f"/api/agent/runs/{suggestion['agent_run_id']}").json()
    assert run["status"] == "succeeded"
    assert run["step_count"] >= 6
    assert run["plan"]
    assert run["plan"][0]["tool"] == "collection_health"
    assert run["skill_id"] == "price_war"
    assert any(item["tool"] == "search_docs" for item in run["plan"])

    kinds = [step["kind"] for step in run["steps"]]
    assert kinds[0] == "context"
    for expected in (
        "plan", "tool", "steward", "analysis", "risk", "verify", "writer",
        "suggestion", "finalize",
    ):
        assert expected in kinds

    tool_names = [step["name"] for step in run["steps"] if step["kind"] == "tool"]
    assert "collection_health" in tool_names
    assert "search_cases" in tool_names
    assert "my_product" in tool_names

    detail = client.get(f"/api/events/{event['id']}").json()
    assert detail["evidence"]
    assert detail["suggestion"]["agent_run_id"] == suggestion["agent_run_id"]


def test_failed_verification_marks_run_failed(monkeypatch):
    event = _ingest_event()

    def bad_analysis(**kwargs):
        return agent.Analysis(
            action="follow",
            confidence=0.9,
            narrative="证据不存在",
            evidence_ids=["snap:forged"],
            generated_by="test",
        )

    monkeypatch.setattr(agent, "analyze", bad_analysis)
    response = client.post(f"/api/events/{event['id']}/analyze")
    assert response.status_code == 409

    runs = client.get("/api/agent/runs").json()
    failed = next(run for run in runs if run["status"] == "failed")
    assert "verification" in (failed["error"] or "")


def test_agent_runs_filter_and_shape():
    event = _ingest_event()
    client.post(f"/api/events/{event['id']}/analyze")

    runs = client.get("/api/agent/runs", params={"event_id": event["id"]}).json()
    assert len(runs) == 1
    assert runs[0]["event_id"] == event["id"]
    assert runs[0]["target_title"] == "竞品A·洗护套装"
    assert isinstance(runs[0]["plan"], list)


def test_agent_run_not_found():
    assert client.get("/api/agent/runs/missing").status_code == 404


def test_analyze_missing_event_is_404():
    assert client.post("/api/events/missing/analyze").status_code == 404


def test_parse_tool_calls():
    payload = {
        "message": {
            "tool_calls": [
                {"function": {"name": "price_history", "arguments": {"target_id": "t1"}}},
                {"function": {"name": "unknown_tool", "arguments": {}}},
                {"function": {"name": "search_cases", "arguments": "{\"query\": \"降价\"}"}},
            ]
        }
    }
    plan = agent.parse_tool_calls(payload, {"price_history", "search_cases"})
    assert [item["tool"] for item in plan] == ["price_history", "search_cases"]
    assert plan[1]["args"]["query"] == "降价"


def test_parse_tool_calls_skips_bad_arguments():
    payload = {
        "message": {
            "tool_calls": [
                {"function": {"name": "price_history", "arguments": "not-json"}},
            ]
        }
    }
    assert agent.parse_tool_calls(payload, {"price_history"}) == []
