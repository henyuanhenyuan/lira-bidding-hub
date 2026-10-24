from fastapi.testclient import TestClient

from app import db, inbox
from app.main import app

client = TestClient(app)
TS = "2026-10-24T02:17:00+08:00"


def _ingest(target_id: str = "t-shot", screenshot_ref: str | None = None):
    snap = {
        "target_id": target_id,
        "ts": TS,
        "collector": "yd-v1",
        "source_tier": 3,
        "observation": {"list_price": 99, "title": "竞品X"},
    }
    if screenshot_ref is not None:
        snap["screenshot_ref"] = screenshot_ref
    return client.post("/v1/ingest/snapshots", json={"snapshots": [snap]})


def test_screenshot_ref_persisted():
    assert _ingest(screenshot_ref="evidence/shot-1.png").status_code == 200
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT screenshot_ref FROM snapshot WHERE target_id = ?", ("t-shot",)
        ).fetchone()
    assert row["screenshot_ref"] == "evidence/shot-1.png"


def test_freshness_reports_latest_snapshot():
    _ingest(target_id="t-fresh")
    body = client.get("/api/freshness").json()
    assert body["latest_ts"] == TS
    assert body["lag_hours"] is not None
    assert body["sla_hours"] > 0


def test_ops_exposes_collection_health():
    _ingest(target_id="t-health")
    body = client.get("/api/ops").json()
    names = [c["collector"] for c in body["collection"]]
    assert "yd-v1" in names
    assert body["freshness"]["latest_ts"] == TS
    assert body["inbox"]["failed"] == 0


def test_failed_inbox_files_visible():
    path = inbox._failed_dir() / "broken.csv"
    path.write_text("bad", encoding="utf-8")
    try:
        body = client.get("/api/ops").json()
        assert body["inbox"]["failed"] >= 1
        assert any(f["name"] == "broken.csv" for f in body["inbox"]["failed_files"])
    finally:
        path.unlink(missing_ok=True)
