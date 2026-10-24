from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

from fastapi import HTTPException, Request

from . import config, db

AUTH_ENABLED = os.getenv("LIRA_AUTH", "off") == "on"
COOKIE = "lira_session"
TTL_SECONDS = 12 * 3600

INGEST_TOKEN = os.getenv("LIRA_INGEST_TOKEN", "")
COOKIE_SECURE = os.getenv("LIRA_COOKIE_SECURE", "off") == "on"
LOGIN_MAX_ATTEMPTS = int(os.getenv("LIRA_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_S = 60

_login_hits: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _secret() -> bytes:
    path = config.DATA_DIR / "secret.key"
    if path.exists():
        return path.read_bytes()
    config.ensure_dirs()
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    return key


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$", 2)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def issue_token(username: str) -> str:
    exp = int(time.time()) + TTL_SECONDS
    payload = f"{username}:{exp}".encode()
    sig = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(payload).decode() + "." + sig


def verify_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(raw.encode())
    except Exception:
        return None
    expect = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        username, exp = payload.decode().split(":")
        expires_at = int(exp)
    except (UnicodeDecodeError, ValueError):
        return None
    if expires_at < time.time():
        return None
    return username


def ensure_default_admin(conn) -> str | None:
    if not AUTH_ENABLED:
        return None
    exists = conn.execute("SELECT COUNT(*) c FROM app_user").fetchone()["c"]
    if exists:
        return None
    conn.execute(
        "INSERT INTO app_user (username, password_hash, role, created_at)"
        " VALUES (?,?,?,?)",
        ("admin", hash_password("admin123"), "admin", db.now_iso()),
    )
    return "admin"


def role_of(actor: str) -> str:
    """鉴权关闭时单人使用，视为 admin。"""
    if not AUTH_ENABLED:
        return "admin"
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT role FROM app_user WHERE username = ?", (actor,)
        ).fetchone()
    return row["role"] if row else "member"


def current_user(request: Request) -> str:
    """鉴权关闭时允许用 X-Actor 头声明操作者，用于留痕。"""
    if not AUTH_ENABLED:
        return request.headers.get("X-Actor") or "local"

    username = verify_token(request.cookies.get(COOKIE))
    if not username:
        raise HTTPException(401, "login required")
    return username


def optional_user(request: Request) -> str | None:
    if not AUTH_ENABLED:
        return request.headers.get("X-Actor") or "local"
    return verify_token(request.cookies.get(COOKIE))


def require_role(*roles: str):
    """角色依赖。鉴权关闭时视为 admin，保持单机体验不变。"""

    def dependency(request: Request) -> str:
        actor = current_user(request)
        if AUTH_ENABLED and role_of(actor) not in roles:
            raise HTTPException(403, "forbidden")
        return actor

    return dependency


def bearer_matches(request: Request) -> bool:
    """采集端用服务令牌写入，避免为了加登录而打断 RPA。"""
    if not INGEST_TOKEN:
        return False
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return False
    return hmac.compare_digest(raw[7:], INGEST_TOKEN)


def check_login_rate(key: str) -> None:
    now = time.time()
    with _login_lock:
        hits = [t for t in _login_hits.get(key, []) if now - t < LOGIN_WINDOW_S]
        if len(hits) >= LOGIN_MAX_ATTEMPTS:
            raise HTTPException(429, "尝试过于频繁，请稍后再试")
        hits.append(now)
        _login_hits[key] = hits


def reset_login_rate(key: str | None = None) -> None:
    with _login_lock:
        if key is None:
            _login_hits.clear()
        else:
            _login_hits.pop(key, None)
