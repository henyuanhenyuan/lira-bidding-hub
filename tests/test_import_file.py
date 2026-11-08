from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_csv_import():
    csv = (
        "target_id,ts,list_price,title,source_tier\n"
        "f1,2026-11-08T10:00:00+08:00,199,竞品F,1\n"
        "f1,2026-11-09T10:00:00+08:00,179,竞品F,1\n"
    )
    response = client.post(
        "/api/import/file",
        files={"file": ("snapshots.csv", csv.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rows_ok"] == 2
    assert body["errors"] == []


def test_json_import():
    payload = {
        "snapshots": [
            {
                "target_id": "f2",
                "ts": "2026-11-09T10:00:00+08:00",
                "collector": "file",
                "source_tier": 2,
                "observation": {"list_price": 88, "title": "竞品G"},
            }
        ]
    }
    response = client.post(
        "/api/import/file",
        files={"file": ("snapshots.json", __import__("json").dumps(payload).encode(), "application/json")},
    )
    assert response.status_code == 200
    assert response.json()["rows_ok"] == 1


def test_bad_rows_reported():
    csv = "target_id,ts,list_price\nf3,2026-11-09T10:00:00+08:00,abc\n,2026-11-09T10:00:00+08:00,10\n"
    body = client.post(
        "/api/import/file",
        files={"file": ("bad.csv", csv.encode("utf-8"), "text/csv")},
    ).json()
    assert body["ok"] is False
    assert len(body["errors"]) == 2


def test_source_settings_roundtrip():
    view = client.get("/api/settings/sources").json()
    assert "taobao" in view and "octoparse" in view and "ingest" in view

    updated = client.post(
        "/api/settings/sources",
        json={"taobao_app_key": "app-key", "octoparse_token": "tok"},
    ).json()
    assert updated["taobao"]["app_key"] == "app-key"
    assert updated["octoparse"]["has_token"] is True
    assert "token" not in updated["octoparse"]
