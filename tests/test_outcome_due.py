from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import db, notify, outcome
from app.main import app

client = TestClient(app)


def _seed_executed(days_ago: int = 8):
    now = datetime.now(timezone.utc)
    executed = (now - timedelta(days=days_ago)).isoformat(timespec="seconds")
    after = now.isoformat(timespec="seconds")
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, external_id, title, my_sku, my_price, active)"
            " VALUES ('t1','taobao','t1','竞品A·洗护套装','SKU-A',289,1)"
        )
        conn.execute(
            "INSERT INTO price_point (target_id, ts, price_low, price_high, confidence,"
            " missing_fields, discontinuity) VALUES ('t1',?,198,200,0.8,'[]',0)",
            (executed,),
        )
        conn.execute(
            "INSERT INTO price_point (target_id, ts, price_low, price_high, confidence,"
            " missing_fields, discontinuity) VALUES ('t1',?,208,210,0.8,'[]',0)",
            (after,),
        )
        conn.execute(
            "INSERT INTO event (id, target_id, ts, type, severity, gate_level, suppressed,"
            " note, evidence, rule_version) VALUES ('e1','t1',?,'price_drop','L2',"
            "'strong',0,'到手价下降','[]','rules-v1')",
            (executed,),
        )
        conn.execute(
            "INSERT INTO suggestion (id, event_id, action, impact_low, impact_high,"
            " confidence, gate_level, narrative, generated_by, status, created_at,"
            " executed_price, executed_at)"
            " VALUES ('s1','e1','follow',1.0,2.0,0.8,'strong','跟进','template:v1',"
            "'executed',?,199,?)",
            (executed, executed),
        )
    return executed


def test_due_list_computes_observed_price_change():
    _seed_executed(8)
    with db.get_db() as conn:
        rows = outcome.due_list(conn, 7)
    assert len(rows) == 1
    row = rows[0]
    assert row["due"] is True
    assert row["days_overdue"] > 0.5
    assert row["observed"]["baseline_price"] == 199.0
    assert row["observed"]["after_price"] == 209.0
    assert row["observed"]["delta_pct"] == 0.0503


def test_notify_due_is_deduplicated(monkeypatch):
    _seed_executed(8)
    sent = []
    monkeypatch.setattr(notify, "send", lambda text: sent.append(text) or True)

    with db.get_db() as conn:
        assert outcome.notify_due(conn, 7) == 1
        assert outcome.notify_due(conn, 7) == 0

    assert sent and "结果回收" in sent[0]


def test_api_due_list_and_record_removes_item():
    _seed_executed(8)
    rows = client.get("/api/outcomes/due", params={"days": 7}).json()
    assert len(rows) == 1
    suggestion_id = rows[0]["id"]
    assert rows[0]["observed"]["after_price"] == 209.0

    recorded = client.post(
        f"/api/suggestions/{suggestion_id}/outcome",
        json={"result": "improved"},
    )
    assert recorded.status_code == 200
    assert client.get("/api/outcomes/due", params={"days": 7}).json() == []


def test_not_due_yet_is_excluded():
    _seed_executed(3)
    with db.get_db() as conn:
        rows = outcome.due_list(conn, 7)
    assert rows[0]["due"] is False
    assert rows[0]["days_overdue"] < 0
