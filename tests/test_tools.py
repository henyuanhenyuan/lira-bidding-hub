import pytest
from fastapi.testclient import TestClient

from app import cases, db, tools
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


def test_collection_health_tool():
    _ingest_event()
    result = tools.call_tool("collection_health", {})
    assert "freshness" in result
    assert any(item["collector"] == "yd-v1" for item in result["collectors"])


def test_price_history_tool():
    event = _ingest_event()
    result = tools.call_tool(
        "price_history", {"target_id": event["target_id"], "days": 30}
    )
    assert result["count"] >= 1
    assert result["points"][0]["price_low"] is not None


def test_search_cases_tool():
    with db.get_db() as conn:
        cases.seed(conn)
    result = tools.call_tool("search_cases", {"query": "大促前降价", "limit": 3})
    assert result["count"] >= 1
    assert result["cases"][0]["attribution"]


def test_my_product_and_simulate_price():
    _ingest_event()
    client.post(
        "/api/my-products",
        json={
            "sku": "SKU-A", "title": "洗护套装", "price": 289,
            "cost": 180, "margin_floor": 0.15,
        },
    )
    client.patch("/api/targets/t1", json={"my_sku": "SKU-A", "my_price": 289})

    product = tools.call_tool("my_product", {"target_id": "t1"})
    assert product["configured"] is True
    assert product["cost"] == 180

    simulated = tools.call_tool(
        "simulate_price", {"target_id": "t1", "new_price": 250}
    )
    assert simulated["guardrail"] in ("ok", "warning", "blocked", "unknown")
    assert simulated["delta_vs_my_price"] == -39.0


def test_get_event_tool():
    event = _ingest_event()
    result = tools.call_tool("get_event", {"event_id": event["id"]})
    assert result["id"] == event["id"]
    assert isinstance(result["evidence"], list)
    assert result["price_point"] is not None


def test_unknown_tool_rejected():
    with pytest.raises(tools.ToolError):
        tools.call_tool("delete_everything", {})


def test_missing_required_arg_rejected():
    with pytest.raises(tools.ToolError):
        tools.call_tool("price_history", {})
