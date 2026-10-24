from fastapi.testclient import TestClient

from app import stream
from app.main import app

client = TestClient(app)


def _payload():
    return {
        "snapshots": [
            {
                "target_id": "t-sse", "ts": "2026-10-23T02:17:00+08:00",
                "collector": "yd-v1", "source_tier": 3,
                "observation": {"list_price": 299, "title": "竞品SSE"},
            },
            {
                "target_id": "t-sse", "ts": "2026-10-24T02:17:00+08:00",
                "collector": "yd-v1", "source_tier": 3,
                "observation": {"list_price": 199, "title": "竞品SSE"},
            },
        ]
    }


def test_broker_publish_subscribe():
    q = stream.subscribe()
    try:
        stream.publish("event", {"id": "e1", "severity": "L1"})
        payload = q.get(timeout=2)
        assert payload["kind"] == "event"
        assert payload["data"]["id"] == "e1"
        text = stream.format_sse(payload)
        assert "event: event" in text
        assert '"severity": "L1"' in text
    finally:
        stream.unsubscribe(q)


def test_ingest_publishes_to_stream():
    q = stream.subscribe()
    try:
        assert client.post("/v1/ingest/snapshots", json=_payload()).status_code == 200
        payload = q.get(timeout=2)
        assert payload["kind"] == "event"
        assert payload["data"]["target_id"] == "t-sse"
    finally:
        stream.unsubscribe(q)


def test_unsubscribe_stops_delivery():
    q = stream.subscribe()
    stream.unsubscribe(q)
    stream.publish("event", {"id": "e2"})
    assert q.empty()
