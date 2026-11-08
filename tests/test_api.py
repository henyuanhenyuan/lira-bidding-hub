from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

D1 = "2026-10-23T02:17:00+08:00"
D2 = "2026-10-24T02:17:00+08:00"


def payload():
    return {
        "snapshots": [
            {
                "target_id": "t1", "ts": D1, "collector": "yd-v1", "source_tier": 3,
                "observation": {
                    "list_price": 299, "coupons": [], "promotions": [],
                    "coin": {"rate": 0, "cap": 0}, "title": "竞品A·洗护套装",
                },
            },
            {
                "target_id": "t1", "ts": D2, "collector": "yd-v1", "source_tier": 3,
                "observation": {
                    "list_price": 299,
                    "coupons": [{"kind": "shop", "threshold": 299, "discount": 30}],
                    "promotions": [], "coin": {"rate": 0, "cap": 0}, "title": "竞品A·洗护套装",
                },
            },
        ]
    }


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_ingest_then_list_events():
    r = client.post("/v1/ingest/snapshots", json=payload())
    assert r.status_code == 200
    body = r.json()
    assert body["rows_ok"] == 2

    events = client.get("/api/events").json()
    assert len(events) >= 1
    assert events[0]["type"] in ("price_drop", "band_breach")


def test_analyze_produces_suggestion_with_valid_evidence():
    client.post("/v1/ingest/snapshots", json=payload())
    ev = client.get("/api/events").json()[0]

    r = client.post(f"/api/events/{ev['id']}/analyze")
    assert r.status_code == 200
    s = r.json()
    assert s["generated_by"].startswith("template")  # LLM 关闭，走确定性回退
    assert s["narrative"]
    assert s["confidence"] > 0

    detail = client.get(f"/api/events/{ev['id']}").json()
    assert detail["evidence"]
    assert set(detail["evidence"]).issubset(set(ev["evidence"]))


def test_approval_workflow_endpoints():
    client.post("/v1/ingest/snapshots", json=payload())
    ev = client.get("/api/events").json()[0]
    s = client.post(f"/api/events/{ev['id']}/analyze").json()
    assert s["guardrail"] in ("ok", "warning", "blocked", "unknown")

    r = client.post(f"/api/suggestions/{s['id']}/submit", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted"

    inbox = client.get("/api/approvals/inbox").json()
    assert any(x["id"] == s["id"] for x in inbox)

    r = client.post(f"/api/suggestions/{s['id']}/approve", json={})
    assert r.json()["status"] == "approved"

    r = client.post(f"/api/suggestions/{s['id']}/execute", json={"executed_price": 280})
    assert r.json()["status"] == "executed"
    assert r.json()["executed_price"] == 280

    logs = client.get(f"/api/suggestions/{s['id']}/timeline").json()
    assert [x["action"] for x in logs] == ["submit", "approve", "execute"]


def test_events_filter_by_target():
    client.post("/v1/ingest/snapshots", json=payload())
    rows = client.get("/api/events").json()
    assert rows
    target_id = rows[0]["target_id"]
    filtered = client.get("/api/events", params={"target_id": target_id}).json()
    assert filtered
    assert all(row["target_id"] == target_id for row in filtered)


def test_target_detail_endpoint():
    client.post("/v1/ingest/snapshots", json=payload())
    res = client.get("/api/targets/t1")
    assert res.status_code == 200
    assert res.json()["id"] == "t1"
    assert client.get("/api/targets/missing").status_code == 404


def test_suggestion_detail_endpoint():
    client.post("/v1/ingest/snapshots", json=payload())
    event = client.get("/api/events").json()[0]
    suggestion = client.post(f"/api/events/{event['id']}/analyze").json()

    res = client.get(f"/api/suggestions/{suggestion['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == suggestion["id"]
    assert body["event"]["id"] == event["id"]
    assert isinstance(body["event"]["evidence"], list)
    assert client.get("/api/suggestions/missing").status_code == 404


def test_price_series_endpoint():
    client.post("/v1/ingest/snapshots", json=payload())
    r = client.get("/api/targets/t1/prices")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert rows[-1]["ts"] == D2


def test_seed_cases_and_search_endpoint():
    r = client.post("/api/cases/seed")
    assert r.status_code == 200
    assert r.json()["total"] >= 3

    s = client.get("/api/cases/search", params={"q": "大促前降价", "event_type": "price_drop"})
    assert s.status_code == 200
    assert len(s.json()) >= 1


def test_analysis_cites_similar_cases():
    client.post("/api/cases/seed")
    client.post("/v1/ingest/snapshots", json=payload())
    ev = client.get("/api/events").json()[0]

    s = client.post(f"/api/events/{ev['id']}/analyze").json()
    assert s["case_ids"], "应当引用至少一条历史案例"
    assert s["similar_cases"]

    detail = client.get(f"/api/events/{ev['id']}").json()
    assert detail["similar_cases"]
    assert any(e.startswith("case:") for e in detail["evidence"])


def test_validate_batch_reports_missing_price():
    r = client.post("/v1/ingest/validate", json={
        "snapshots": [{
            "target_id": "t9", "ts": D1, "collector": "x", "source_tier": 4,
            "observation": {"list_price": None},
        }]
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["errors"][0]["error"]


def test_products_seed_and_mapping_flow():
    client.post("/v1/ingest/snapshots", json={"snapshots": payload()["snapshots"][:1]})
    client.post("/api/my-products/seed")

    s = client.post("/api/mappings/suggest")
    assert s.status_code == 200

    pending = client.get("/api/mappings", params={"status": "pending"}).json()
    assert pending, "应至少生成一条候选"

    decided = client.post(
        f"/api/mappings/{pending[0]['id']}/decide",
        json={"decision": "confirmed"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "confirmed"

    targets = client.get("/api/targets").json()
    assert targets[0]["mapping_status"] == "mapped"
    assert targets[0]["my_price"] is not None


def test_ops_state_and_manual_run():
    o = client.get("/api/ops").json()
    assert "scheduler" in o and "metrics" in o

    r = client.post("/api/ops/run", params={"kind": "backup"})
    assert r.status_code == 200
    assert r.json()["kind"] == "backup"


def test_outcome_endpoint_after_execute():
    client.post("/v1/ingest/snapshots", json=payload())
    ev = client.get("/api/events").json()[0]
    s = client.post(f"/api/events/{ev['id']}/analyze").json()
    client.post(f"/api/suggestions/{s['id']}/submit", json={})
    client.post(f"/api/suggestions/{s['id']}/approve", json={})
    client.post(f"/api/suggestions/{s['id']}/execute", json={"executed_price": 280})

    r = client.post(
        f"/api/suggestions/{s['id']}/outcome",
        json={"result": "improved", "note": "转化提升"},
    )
    assert r.status_code == 200
    assert r.json()["case_id"]

    got = client.get(f"/api/suggestions/{s['id']}/outcome")
    assert got.status_code == 200
    assert got.json()["result"] == "improved"


def test_insight_404_without_reviews():
    client.post("/v1/ingest/snapshots", json={"snapshots": payload()["snapshots"][:1]})
    r = client.post("/api/targets/t1/insights", params={"window_days": 7})
    assert r.status_code == 404


def test_patch_target_sets_my_price():
    client.post("/v1/ingest/snapshots", json={"snapshots": payload()["snapshots"][:1]})
    r = client.patch("/api/targets/t1", json={"my_price": 260, "my_sku": "SKU-A"})
    assert r.status_code == 200
    assert r.json()["my_price"] == 260
