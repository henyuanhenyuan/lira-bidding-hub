import base64
import hashlib
import hmac

from fastapi.testclient import TestClient

from app import auth, db
from app.main import app


def _seed(username: str, role: str, password: str = "pw123456") -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO app_user (username, password_hash, role, created_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT (username) DO UPDATE SET password_hash=excluded.password_hash,"
            " role=excluded.role, created_at=excluded.created_at",
            (username, auth.hash_password(password), role, db.now_iso()),
        )


def _auth_on(monkeypatch) -> None:
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    auth.reset_login_rate()


def test_password_hash_roundtrip():
    stored = auth.hash_password("s3cret")
    assert stored.startswith("pbkdf2$")
    assert auth.verify_password("s3cret", stored)
    assert not auth.verify_password("wrong", stored)


def test_verify_rejects_malformed_hash():
    assert auth.verify_password("x", "not-a-hash") is False


def test_token_roundtrip():
    token = auth.issue_token("alice")
    assert auth.verify_token(token) == "alice"


def test_token_tamper_rejected():
    token = auth.issue_token("alice")
    payload, sig = token.rsplit(".", 1)
    assert auth.verify_token(payload + ".deadbeef") is None


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(auth, "TTL_SECONDS", -10)
    token = auth.issue_token("bob")
    assert auth.verify_token(token) is None


def test_token_with_bad_exp_returns_none():
    payload = b"alice:notanint"
    raw = base64.urlsafe_b64encode(payload).decode()
    sig = hmac.new(auth._secret(), payload, hashlib.sha256).hexdigest()[:32]
    assert auth.verify_token(f"{raw}.{sig}") is None


def test_create_user_requires_admin(monkeypatch):
    _auth_on(monkeypatch)
    _seed("boss", "admin")
    _seed("ops", "member")
    client = TestClient(app)

    assert client.post("/api/login", json={"username": "ops", "password": "pw123456"}).status_code == 200
    denied = client.post(
        "/api/users", json={"username": "evil", "password": "pw123456", "role": "admin"}
    )
    assert denied.status_code == 403

    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "boss", "password": "pw123456"}).status_code == 200
    assert client.post(
        "/api/users", json={"username": "new", "password": "pw123456", "role": "manager"}
    ).status_code == 200
    assert client.post(
        "/api/users", json={"username": "bad", "password": "pw123456", "role": "root"}
    ).status_code == 400


def test_list_users_requires_admin(monkeypatch):
    _auth_on(monkeypatch)
    _seed("boss", "admin")
    _seed("ops", "member")
    client = TestClient(app)
    client.post("/api/login", json={"username": "ops", "password": "pw123456"})
    assert client.get("/api/users").status_code == 403
    client.post("/api/logout")
    client.post("/api/login", json={"username": "boss", "password": "pw123456"})
    assert client.get("/api/users").status_code == 200


def test_ops_requires_admin(monkeypatch):
    _auth_on(monkeypatch)
    _seed("boss", "admin")
    _seed("ops", "member")
    client = TestClient(app)
    client.post("/api/login", json={"username": "ops", "password": "pw123456"})
    assert client.get("/api/ops").status_code == 403
    client.post("/api/logout")
    client.post("/api/login", json={"username": "boss", "password": "pw123456"})
    assert client.get("/api/ops").status_code == 200


def test_data_requires_login_when_auth_on(monkeypatch):
    _auth_on(monkeypatch)
    client = TestClient(app)
    assert client.get("/api/events").status_code == 401
    assert client.get("/api/targets").status_code == 401


def test_root_redirects_to_login(monkeypatch):
    _auth_on(monkeypatch)
    client = TestClient(app)
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/next/login"
    page = client.get("/login", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/next/login"


def test_ingest_token_allows_rpa(monkeypatch):
    _auth_on(monkeypatch)
    monkeypatch.setattr(auth, "INGEST_TOKEN", "rpa-secret")
    client = TestClient(app)
    body = {
        "snapshots": [{
            "target_id": "t9", "ts": "2026-10-24T02:17:00+08:00",
            "collector": "yd-v1", "source_tier": 3,
            "observation": {"list_price": 99, "title": "竞品X"},
        }]
    }
    ok = client.post(
        "/v1/ingest/snapshots", json=body,
        headers={"Authorization": "Bearer rpa-secret"},
    )
    assert ok.status_code == 200
    denied = client.post(
        "/v1/ingest/snapshots", json=body,
        headers={"Authorization": "Bearer wrong"},
    )
    assert denied.status_code == 401


def test_me_returns_role(monkeypatch):
    _auth_on(monkeypatch)
    _seed("boss", "admin")
    client = TestClient(app)
    client.post("/api/login", json={"username": "boss", "password": "pw123456"})
    body = client.get("/api/me").json()
    assert body == {
        "auth": True, "username": "boss", "display_name": "boss",
        "role": "admin", "role_text": "管理员",
    }


def test_login_rate_limited(monkeypatch):
    _auth_on(monkeypatch)
    monkeypatch.setattr(auth, "LOGIN_MAX_ATTEMPTS", 2)
    auth.reset_login_rate()
    _seed("boss", "admin")
    client = TestClient(app)
    first = client.post("/api/login", json={"username": "boss", "password": "wrong"})
    second = client.post("/api/login", json={"username": "boss", "password": "wrong"})
    third = client.post("/api/login", json={"username": "boss", "password": "wrong"})
    assert [first.status_code, second.status_code] == [401, 401]
    assert third.status_code == 429
    auth.reset_login_rate()
