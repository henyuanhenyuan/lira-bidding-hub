from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app import autopilot, db, pricing
from app.contracts import PricePoint
from app.main import app

client = TestClient(app)


def _observation(price: float) -> dict:
    return {
        "list_price": price,
        "coupons": [],
        "promotions": [],
        "coin": {"rate": 0, "cap": 0},
    }


def _snapshots(target_id: str, first: float, second: float, region: str = "杭州"):
    return {
        "snapshots": [
            {
                "target_id": target_id, "ts": "2026-10-20T02:00:00+08:00",
                "collector": "test", "source_tier": 1,
                "observation": _observation(first),
            },
            {
                "target_id": target_id, "ts": "2026-10-21T02:00:00+08:00",
                "collector": "test", "source_tier": 1,
                "observation": {**_observation(second), "region": region},
            },
        ]
    }


def _prepare(target_id: str, my_price: float = 250.0, cost: float = 150.0):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, title, my_sku, my_price, region,"
            " pricing_strategy, active) VALUES (?,?,?,?,?,?,?,1)",
            (target_id, "taobao", "竞品A", f"sku-{target_id}", my_price, "杭州", "follow"),
        )
        conn.execute(
            "INSERT INTO my_product (sku, title, price, cost, margin_floor, active)"
            " VALUES (?,?,?,?,?,1)",
            (f"sku-{target_id}", "我方商品", my_price, cost, 0.15),
        )


def _analyze_latest(target_id: str) -> dict:
    events = [
        event for event in client.get("/api/events").json()
        if event["target_id"] == target_id
    ]
    event = max(events, key=lambda row: row["ts"])
    return client.post(f"/api/events/{event['id']}/analyze").json()


# ---------------- 调价策略 ----------------

def _point(value: float) -> PricePoint:
    return PricePoint(
        target_id="t", ts="2026-10-21T00:00:00+08:00", point=value,
        price_low=value * 0.99, price_high=value * 1.01,
        confidence=0.9, missing_fields=[],
    )


def test_pricing_propose_follow_and_floor():
    plan = pricing.propose(
        _point(199), 250, 150, 0.15, strategy="follow", max_delta_pct=0.3
    )
    assert plan.action == "adjust_price"
    assert plan.target_price == 199.0
    assert round(plan.delta_pct, 3) == -0.204
    assert plan.needs_review is False


def test_pricing_never_below_margin_floor():
    plan = pricing.propose(_point(100), 250, 150, 0.15, strategy="follow")
    assert plan.target_price == pricing.floor_price(150, 0.15)
    assert plan.needs_review is True


def test_pricing_deadzone_holds():
    plan = pricing.propose(_point(250.4), 250, 150, 0.15, strategy="follow")
    assert plan.action == "hold"
    assert plan.target_price is None


def test_pricing_undercut():
    plan = pricing.propose(_point(200), 250, 100, 0.15, strategy="undercut", undercut_pct=0.05)
    assert plan.target_price == 190.0


# ---------------- 自动驾驶分流 ----------------

def test_autopilot_auto_executes_within_band(monkeypatch):
    monkeypatch.setenv("LIRA_AUTOPILOT", "on")
    monkeypatch.setenv("LIRA_AUTO_MAX_DELTA", "0.5")
    monkeypatch.setenv("LIRA_AUTO_MIN_CONF", "0.5")
    _prepare("ap-auto")
    client.post("/v1/ingest/snapshots", json=_snapshots("ap-auto", 299, 199))

    suggestion = _analyze_latest("ap-auto")
    assert suggestion["action"] == "adjust_price"
    assert suggestion["autopilot"]["decision"]["mode"] == "auto"

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion["id"],)
        ).fetchone()
        ledger = conn.execute(
            "SELECT * FROM bid_ledger WHERE suggestion_id = ?",
            (suggestion["id"],),
        ).fetchone()
    assert row["status"] == "executed"
    assert row["mode"] == "auto"
    assert row["executed_price"] == 199.0
    assert ledger["status"] == "executed"
    assert ledger["region"] == "杭州"
    assert ledger["to_price"] == 199.0


def test_autopilot_escalates_large_delta(monkeypatch):
    monkeypatch.setenv("LIRA_AUTOPILOT", "on")
    monkeypatch.setenv("LIRA_AUTO_MAX_DELTA", "0.1")
    monkeypatch.setenv("LIRA_AUTO_MIN_CONF", "0.5")
    _prepare("ap-exc")
    client.post("/v1/ingest/snapshots", json=_snapshots("ap-exc", 299, 199))

    suggestion = _analyze_latest("ap-exc")
    assert suggestion["autopilot"]["decision"]["mode"] == "exception"

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion["id"],)
        ).fetchone()
    assert row["status"] == "pending"
    assert row["exception"] == 1
    assert "调价" in (row["exception_reason"] or "")

    items = client.get("/api/autopilot/exceptions").json()["items"]
    assert any(item["id"] == suggestion["id"] for item in items)


def test_autopilot_hold_is_auto_closed(monkeypatch):
    monkeypatch.setenv("LIRA_AUTOPILOT", "on")
    _prepare("ap-hold")
    client.post("/v1/ingest/snapshots", json=_snapshots("ap-hold", 299, 270))

    suggestion = _analyze_latest("ap-hold")
    assert suggestion["action"] == "hold"
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion["id"],)
        ).fetchone()
    assert row["status"] == "auto_closed"
    assert row["exception"] == 0


def test_autopilot_disabled_leaves_manual_queue():
    assert autopilot.config()["enabled"] is False
    _prepare("ap-manual")
    client.post("/v1/ingest/snapshots", json=_snapshots("ap-manual", 299, 199))
    suggestion = _analyze_latest("ap-manual")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion["id"],)
        ).fetchone()
    assert row["status"] == "pending"
    assert row["mode"] == "manual"


def test_resolve_exception_executes(monkeypatch):
    monkeypatch.setenv("LIRA_AUTOPILOT", "on")
    monkeypatch.setenv("LIRA_AUTO_MAX_DELTA", "0.1")
    monkeypatch.setenv("LIRA_AUTO_MIN_CONF", "0.5")
    _prepare("ap-resolve")
    client.post("/v1/ingest/snapshots", json=_snapshots("ap-resolve", 299, 199))
    suggestion = _analyze_latest("ap-resolve")

    result = client.post(
        f"/api/autopilot/exceptions/{suggestion['id']}/resolve",
        json={"approve": True, "note": "人工确认"},
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "executed"
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion["id"],)
        ).fetchone()
    assert row["exception"] == 0
    assert row["executed_price"] == 199.0


# ---------------- 地区与流水 ----------------

def test_dashboard_region_filter_and_ledger(monkeypatch):
    monkeypatch.setenv("LIRA_AUTOPILOT", "on")
    monkeypatch.setenv("LIRA_AUTO_MAX_DELTA", "0.5")
    monkeypatch.setenv("LIRA_AUTO_MIN_CONF", "0.5")
    _prepare("ap-hz")
    _prepare("ap-sh")
    client.post(
        "/v1/ingest/snapshots", json=_snapshots("ap-hz", 299, 199, region="杭州")
    )
    client.post(
        "/v1/ingest/snapshots", json=_snapshots("ap-sh", 299, 199, region="上海")
    )
    _analyze_latest("ap-hz")

    dash = client.get("/api/dashboard?region=杭州").json()
    assert {row["id"] for row in dash["compare"]} == {"ap-hz"}
    assert dash["autopilot"]["auto_executed"] >= 1
    assert dash["autopilot"]["ledger"]

    ledger = client.get("/api/autopilot/ledger?region=杭州").json()["items"]
    assert ledger and all(item["region"] == "杭州" for item in ledger)


# ---------------- Excel 导入 ----------------

def test_excel_import_and_region(monkeypatch):
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["target_id", "ts", "list_price", "title", "region"])
    sheet.append(["xlsx-1", "2026-10-22T02:00:00+08:00", 88.5, "表格竞品", "成都"])
    buffer = io.BytesIO()
    book.save(buffer)

    response = client.post(
        "/api/import/file",
        files={
            "file": (
                "prices.xlsx", buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_ok"] == 1
    assert body["rows_rejected"] == 0

    with db.get_db() as conn:
        target = conn.execute(
            "SELECT region, title FROM target WHERE id = 'xlsx-1'"
        ).fetchone()
    assert target["region"] == "成都"
    assert target["title"] == "表格竞品"
