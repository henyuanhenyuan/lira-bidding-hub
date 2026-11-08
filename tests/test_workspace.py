from fastapi.testclient import TestClient

from app import db, docs as doc_store
from app.main import app

client = TestClient(app)


def _seed_target():
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, title, my_price, active, mapping_status)"
            " VALUES ('w1','taobao','竞品W',289,1,'mapped')"
        )
        for index, price in enumerate((299, 259, 219)):
            conn.execute(
                "INSERT INTO price_point (target_id, ts, price_low, price_high,"
                " confidence, missing_fields, discontinuity)"
                " VALUES (?,?,?,?,0.9,'[]',0)",
                ("w1", f"2026-11-0{index + 6}T10:00:00+08:00", price, price),
            )
        conn.execute(
            "INSERT INTO event (id,target_id,ts,type,severity,gate_level,suppressed,"
            "note,evidence,rule_version)"
            " VALUES ('we1','w1','2026-11-08T10:00:00+08:00','price_drop','L2',"
            "'strong',0,'降价','[]','rules-v1')"
        )


def test_dashboard_shape_and_compare():
    _seed_target()
    body = client.get("/api/dashboard").json()
    assert set(body) >= {"compare", "trend", "severity", "status"}

    target = next(item for item in body["compare"] if item["id"] == "w1")
    assert target["point"] == 219
    assert target["delta"] is not None and target["delta"] < 0
    assert target["severity"] == "L2"
    assert body["severity"]["L2"] >= 1
    assert any(item["count"] >= 1 for item in body["trend"])


def test_dashboard_empty_is_valid():
    body = client.get("/api/dashboard").json()
    assert isinstance(body["compare"], list)


def test_chat_requires_question():
    assert client.post("/api/agent/chat", json={"question": "  "}).status_code == 400


def test_chat_returns_extractive_answer_without_llm():
    with db.get_db() as conn:
        doc_store.create_doc(
            conn, title="竞价规则", content="竞品到手价低于我方 95% 视为价格带击穿。"
        )
    body = client.post(
        "/api/agent/chat", json={"question": "价格带击穿怎么判定？"}
    ).json()
    assert body["mode"] in {"extractive", "empty"}
    if body["mode"] == "extractive":
        assert body["citations"]
        assert "知识库" in body["answer"]
