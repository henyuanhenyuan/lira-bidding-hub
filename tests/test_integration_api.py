import json

from fastapi.testclient import TestClient

from app import auth, db, eval as eval_store, settings_store
from app.main import app


def test_five_demo_accounts_are_usable():
    auth.reset_login_rate()
    with db.get_db() as conn:
        auth.ensure_accounts(conn)
    client = TestClient(app)
    for account in auth.DEMO_ACCOUNTS:
        response = client.post(
            "/api/login",
            json={"username": account["username"], "password": account["password"]},
        )
        assert response.status_code == 200, account["username"]
        body = response.json()
        assert body["display_name"] == account["display_name"]
        assert body["role"] == account["role"]


def test_integration_token_ingest_and_revoke(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    auth.reset_login_rate()
    with db.get_db() as conn:
        auth.ensure_accounts(conn)
    client = TestClient(app)
    assert client.post(
        "/api/login",
        json={"username": "admin", "password": "Lira@Admin2026"},
    ).status_code == 200

    created = client.post(
        "/api/integration/tokens",
        json={"name": "rpa", "scopes": ["ingest"]},
    )
    assert created.status_code == 200
    token = created.json()["token"]
    assert token.startswith("lm_")

    body = {
        "snapshots": [{
            "target_id": "token-sku",
            "ts": "2026-11-09T10:00:00+08:00",
            "collector": "rpa",
            "source_tier": 2,
            "observation": {"list_price": 128, "title": "令牌接入"},
        }]
    }
    client.cookies.clear()
    assert client.post("/v1/ingest/snapshots", json=body).status_code == 401
    assert client.post(
        "/v1/ingest/snapshots", json=body,
        headers={"Authorization": "Bearer wrong"},
    ).status_code == 401
    ok = client.post(
        "/v1/ingest/snapshots", json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert ok.json()["rows_ok"] == 1

    token_id = created.json()["id"]
    auth.reset_login_rate()
    assert client.post(
        "/api/login",
        json={"username": "admin", "password": "Lira@Admin2026"},
    ).status_code == 200
    assert client.delete(f"/api/integration/tokens/{token_id}").status_code == 200
    client.cookies.clear()
    assert client.post(
        "/v1/ingest/snapshots", json=body,
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 401


def test_integration_test_push_uses_real_pipeline():
    client = TestClient(app)
    response = client.post(
        "/api/integration/test-push",
        json={
            "target_id": "console-sku",
            "title": "控制台推送",
            "price": 88,
            "source_tier": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["rows_ok"] == 1


def test_provider_roundtrip_hides_key_and_probe_missing():
    client = TestClient(app)
    saved = client.post(
        "/api/settings/providers",
        json={
            "providers": [{
                "id": "qwen",
                "name": "通义千问",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "api_key": "sk-test",
                "enabled": True,
            }],
            "active": "qwen",
            "route": "ollama",
        },
    )
    assert saved.status_code == 200
    view = client.get("/api/settings/models").json()
    row = next(item for item in view["providers"] if item["id"] == "qwen")
    assert row["has_key"] is True
    assert row["model"] == "qwen-plus"
    assert "api_key" not in row
    assert client.post("/api/settings/providers/missing/probe").status_code == 404

    settings_store.save(
        {
            "api_providers": [{
                "id": "qwen", "name": "通义千问",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus", "api_key": "", "enabled": True,
            }],
            "active_provider": "qwen",
            "route": "ollama",
            "api_key": "",
        }
    )


def test_finetune_dataset_config_and_validation(tmp_path):
    with db.get_db() as conn:
        eval_store.list_cases(conn)
    client = TestClient(app)

    dataset = client.post("/api/finetune/dataset", json={"limit": 60})
    assert dataset.status_code == 200
    payload = dataset.json()
    assert payload["samples"] > 0
    assert payload["path"].endswith(".jsonl")
    first = open(payload["path"], encoding="utf-8").readline()
    row = json.loads(first)
    assert [item["role"] for item in row["messages"]] == ["system", "user", "assistant"]

    job = client.post(
        "/api/finetune/jobs",
        json={
            "name": "test-lora",
            "base_model": "Qwen/Qwen3-4B",
            "method": "lora",
            "teacher": "qwen-plus",
            "epochs": 1,
            "dataset_path": payload["path"],
        },
    )
    assert job.status_code == 200
    detail = job.json()
    assert detail["config"]["framework"]["trainer"] == "trl.SFTTrainer"
    assert detail["config"]["lora"]["r"] == 16

    validated = client.post(f"/api/finetune/jobs/{detail['id']}/validate")
    assert validated.status_code == 200
    body = validated.json()
    assert body["ok"] is True
    assert "deps_ready" in body
    assert body["train_command"].startswith("python data/finetune/train_lora.py")
