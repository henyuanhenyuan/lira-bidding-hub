from fastapi.testclient import TestClient

from app import config, settings_store
from app.main import app

client = TestClient(app)


def test_defaults_and_roundtrip():
    data = settings_store.load()
    assert data["backend"] in {"gateway", "legacy"}
    settings_store.save({"local_model": "qwen3:14b", "route": "ollama"})
    loaded = settings_store.load()
    assert loaded["local_model"] == "qwen3:14b"
    assert config.OLLAMA_MODEL == "qwen3:14b"
    settings_store.save({"local_model": "qwen3:4b", "route": "auto"})


def test_public_view_hides_key():
    settings_store.save({"api_key": "sk-secret"})
    view = settings_store.public_view()
    assert "api_key" not in view["api"]
    assert view["api"]["has_key"] is True
    settings_store.save({"api_key": ""})


def test_model_settings_api():
    body = client.get("/api/settings/models").json()
    assert "backend" in body and "local" in body

    updated = client.post(
        "/api/settings/models",
        json={
            "backend": "gateway", "route": "ollama",
            "local_model": "qwen3:4b", "local_url": "http://127.0.0.1:11434",
            "api_base_url": "", "api_model": "qwen-plus", "api_key": None,
        },
    ).json()
    assert updated["route"] == "ollama"


def test_probe_endpoint():
    body = client.get("/api/settings/models/probe").json()
    assert "llm_available" in body
