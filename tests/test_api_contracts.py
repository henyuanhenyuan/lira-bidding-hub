from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

REQUIRED = {
    "/api/eval/run",
    "/api/eval/runs",
    "/api/eval/badcases",
    "/api/eval/runs/{run_key}/report",
    "/api/observability/traces",
    "/api/observability/traces/{trace_id}",
    "/api/suggestions/{sid}/risk",
    "/api/llm/stream",
    "/api/events/{event_id}/analyze/stream",
    "/api/skills/{skill_id}/validate",
}


def test_required_routes_exist():
    paths = set(app.openapi()["paths"])
    missing = REQUIRED - paths
    assert not missing, f"缺少路由：{missing}"


def test_eval_runs_endpoint_responds():
    response = client.get("/api/eval/runs?limit=1")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_eval_badcases_endpoint_responds():
    response = client.get("/api/eval/badcases?limit=1")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_observability_traces_endpoint_responds():
    response = client.get("/api/observability/traces?limit=1")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
