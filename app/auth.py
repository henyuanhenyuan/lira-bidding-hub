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

AUTH_ENABLED = os.getenv("LIRA_AUTH", "on") == "on"
COOKIE = "lira_session"
TTL_SECONDS = 12 * 3600

# 演示与交付用的 5 个真实账号：启动时幂等写入，登录即用。
DEMO_ACCOUNTS: tuple[dict[str, str], ...] = (
    {"username": "admin", "password": "Lira@Admin2026", "role": "admin", "display_name": "林澈 · 负责人"},
    {"username": "manager", "password": "Lira@Manager2026", "role": "manager", "display_name": "周遥 · 竞价主管"},
    {"username": "analyst", "password": "Lira@Analyst2026", "role": "manager", "display_name": "陈粟 · 价格分析师"},
    {"username": "operator", "password": "Lira@Ops2026", "role": "member", "display_name": "许棠 · 运营执行"},
    {"username": "viewer", "password": "Lira@View2026", "role": "member", "display_name": "顾言 · 只读观察"},
)
ROLE_TEXT = {"admin": "管理员", "manager": "主管", "member": "成员"}

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


def ensure_accounts(conn) -> list[str]:
    """幂等写入 5 个交付账号；已存在则只补齐展示名，不覆盖密码与角色。"""
    created: list[str] = []
    for item in DEMO_ACCOUNTS:
        row = conn.execute(
            "SELECT username, display_name FROM app_user WHERE username = ?",
            (item["username"],),
        ).fetchone()
        if row:
            if not row["display_name"]:
                conn.execute(
                    "UPDATE app_user SET display_name = ? WHERE username = ?",
                    (item["display_name"], item["username"]),
                )
            continue
        conn.execute(
            "INSERT INTO app_user (username, password_hash, role, display_name, created_at)"
            " VALUES (?,?,?,?,?)",
            (
                item["username"],
                hash_password(item["password"]),
                item["role"],
                item["display_name"],
                db.now_iso(),
            ),
        )
        created.append(item["username"])
    return created


def ensure_default_admin(conn) -> str | None:
    created = ensure_accounts(conn)
    return "admin" if "admin" in created else None


def account_of(actor: str) -> dict[str, str] | None:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT username, role, display_name FROM app_user WHERE username = ?",
            (actor,),
        ).fetchone()
    return dict(row) if row else None


def display_name_of(actor: str) -> str:
    account = account_of(actor)
    if not account:
        return actor
    return account.get("display_name") or actor


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


def bearer_token(request: Request) -> str | None:
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return None
    value = raw[7:].strip()
    return value or None


def token_matches(raw: str) -> bool:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM api_token WHERE token_hash = ? AND revoked_at IS NULL",
            (digest,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE api_token SET last_used_at = ?, call_count = call_count + 1 WHERE id = ?",
            (db.now_iso(), row["id"]),
        )
    return True


def bearer_matches(request: Request) -> bool:
    """采集端用服务令牌写入，避免为了加登录而打断 RPA。"""
    raw = bearer_token(request)
    if not raw:
        return False
    if INGEST_TOKEN and hmac.compare_digest(raw, INGEST_TOKEN):
        return True
    try:
        return token_matches(raw)
    except Exception:
        return False


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
