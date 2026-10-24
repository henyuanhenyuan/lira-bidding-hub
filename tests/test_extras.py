import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import auth, db, images, metrics, rerank, semantic, scheduler
from app.main import app

client = TestClient(app)
D1 = "2026-10-23T02:17:00+08:00"
D2 = "2026-10-24T02:17:00+08:00"


# ---------------- 图像指纹 ----------------

def test_cdn_size_params_do_not_change_fingerprint():
    a = images.fingerprint("https://img.alicdn.com/a/1.jpg?width=400&quality=80")
    b = images.fingerprint("https://img.alicdn.com/a/1.jpg?width=800&quality=60")
    assert a == b


def test_different_paths_change_fingerprint():
    a = images.fingerprint("https://img.alicdn.com/a/1.jpg")
    b = images.fingerprint("https://img.alicdn.com/a/2.jpg")
    assert a != b


def test_explicit_image_hash_wins():
    obs = {"main_image_hash": "abc123", "main_image_url": "https://x/1.jpg"}
    assert images.fp_of(obs) == "abc123"


def test_semantic_ignores_cdn_resize():
    prev = {"title": "A", "main_image_url": "https://cdn/1.jpg?w=400"}
    cur = {"title": "A", "main_image_url": "https://cdn/1.jpg?w=800"}
    assert semantic.detect(prev, cur) == []


def test_semantic_detects_real_image_swap():
    prev = {"title": "A", "main_image_url": "https://cdn/1.jpg"}
    cur = {"title": "A", "main_image_url": "https://cdn/2.jpg"}
    assert [c.field for c in semantic.detect(prev, cur)] == ["image"]


# ---------------- 重排 ----------------

def test_rerank_prefers_matching_band_and_text():
    cases = [
        {"id": "a", "summary": "竞品大促降价", "attribution": "大促试探",
         "price_band": "100-150", "delta_pct": -0.1, "ts": "2026-10-20T00:00:00+00:00"},
        {"id": "b", "summary": "完全无关的内容", "attribution": "无关",
         "price_band": "300-350", "delta_pct": 0.3, "ts": "2020-01-01T00:00:00+00:00"},
    ]
    out = rerank.rerank(
        cases, query="竞品大促降价", price_band="100-150", delta_pct=-0.1, limit=1
    )
    assert out[0]["id"] == "a"


def test_rerank_empty():
    assert rerank.rerank([], query="x", price_band=None, delta_pct=None) == []


# ---------------- 指标 ----------------

def test_metrics_record_and_summary():
    metrics.record("attribution", model="qwen3:4b", ok=True, latency_ms=120)
    metrics.record("attribution", model="qwen3:4b", ok=False, fallback=True,
                   latency_ms=800, detail="timeout")
    with db.get_db() as conn:
        s = metrics.summary(conn, 24)
    assert s["calls"] >= 2
    assert 0 <= s["fallback_rate"] <= 1
    assert s["p95_latency_ms"] is not None


# ---------------- 账号 ----------------

def seed_user(name="alice", role="member", password="secret123"):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO app_user (username, password_hash, role, created_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT (username) DO UPDATE SET password_hash=excluded.password_hash,"
            " role=excluded.role, created_at=excluded.created_at",
            (name, auth.hash_password(password), role, db.now_iso()),
        )


def test_change_password_requires_old_when_self(monkeypatch):
    seed_user()
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)

    login = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert login.status_code == 200

    r = client.post("/api/users/alice/password", json={"new_password": "newpass123"})
    assert r.status_code == 403

    r = client.post(
        "/api/users/alice/password",
        json={"new_password": "newpass123", "old_password": "secret123"},
    )
    assert r.status_code == 200
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM app_user WHERE username='alice'"
        ).fetchone()
    assert auth.verify_password("newpass123", row["password_hash"])

    client.post("/api/logout")


def test_short_password_rejected():
    seed_user()
    r = client.post("/api/users/alice/password", json={"new_password": "123"})
    assert r.status_code == 400


def test_set_role_validates_value():
    seed_user()
    r = client.patch("/api/users/alice", json={"role": "root"})
    assert r.status_code == 400
    r = client.patch("/api/users/alice", json={"role": "manager"})
    assert r.status_code == 200
    assert r.json()["role"] == "manager"


# ---------------- holdout ----------------

def _payload(ts, price):
    return {"snapshots": [{
        "target_id": "t1", "ts": ts, "collector": "yd-v1", "source_tier": 3,
        "observation": {"list_price": price, "coupons": [], "promotions": [],
                        "coin": {"rate": 0, "cap": 0}, "title": "竞品A·洗护套装"},
    }]}


def test_holdout_target_gets_holdout_suggestion():
    client.post("/v1/ingest/snapshots", json=_payload(D1, 299))
    client.patch("/api/targets/t1", json={"holdout": True})
    client.post("/v1/ingest/snapshots", json=_payload(D2, 239))

    ev = client.get("/api/events").json()[0]
    s = client.post(f"/api/events/{ev['id']}/analyze").json()
    assert s["status"] == "holdout"

    # holdout 不进审批箱
    assert all(x["id"] != s["id"] for x in client.get("/api/approvals/inbox").json())

    # 也不能被提交
    r = client.post(f"/api/suggestions/{s['id']}/submit", json={})
    assert r.status_code == 400


def test_holdout_report_shape():
    r = client.get("/api/experiments/holdout")
    assert r.status_code == 200
    body = r.json()
    assert {"treatment", "control", "holdout_targets"} <= set(body)
    assert "improvement_rate" in body["treatment"]


# ---------------- 并发 ----------------

def test_concurrent_reads_are_stable():
    client.post("/v1/ingest/snapshots", json=_payload(D1, 299))

    def hit(i):
        path = "/api/health" if i % 2 == 0 else "/api/events"
        return client.get(path).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(hit, range(32)))
    assert codes.count(200) == 32
