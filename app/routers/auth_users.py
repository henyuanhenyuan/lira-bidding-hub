from __future__ import annotations

import json
import queue
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import (
    agent, agent_graph, alignment, approval, auth, collect_logs, collect_tasks,
    collectors,
    config, db, docs as doc_store, eval as eval_store,
    executor, gates, guardrail, ingest, metrics,
    review_queue, scheduler, skills, stream, tracing,
    vectorstore,
)
from .. import llm
from .. import outcome as outcome_store
from .. import cases as case_store
from ..contracts import IngestBatch, PricePoint, SnapshotIn
from ..evaluation import report as eval_report
from ..evaluation import runner as eval_runner
from .common import _payload

router = APIRouter()


# ---------------- 账号 ----------------

class LoginIn(BaseModel):
    username: str
    password: str

@router.post("/api/login")
def login(body: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    ip = request.client.host if request.client else "unknown"
    auth.check_login_rate(ip)
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM app_user WHERE username = ?", (body.username,)
        ).fetchone()
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    auth.reset_login_rate(ip)
    response.set_cookie(
        auth.COOKIE, auth.issue_token(body.username),
        httponly=True, samesite="lax", secure=auth.COOKIE_SECURE,
        max_age=auth.TTL_SECONDS,
    )
    return {
        "username": body.username,
        "role": row["role"],
        "display_name": row["display_name"] or body.username,
        "role_text": auth.ROLE_TEXT.get(row["role"], row["role"]),
    }

@router.post("/api/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}

@router.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    if not auth.AUTH_ENABLED:
        actor = request.headers.get("X-Actor") or "local"
        return {
            "auth": False, "actor": actor, "username": actor,
            "display_name": "本地模式", "role": "admin", "role_text": "管理员",
        }
    username = auth.verify_token(request.cookies.get(auth.COOKIE))
    if not username:
        raise HTTPException(401, "login required")
    account = auth.account_of(username) or {}
    role = account.get("role", "member")
    return {
        "auth": True,
        "username": username,
        "display_name": account.get("display_name") or username,
        "role": role,
        "role_text": auth.ROLE_TEXT.get(role, role),
    }

@router.get("/api/users")
def list_users(
    actor: str = Depends(auth.require_role("admin")),
) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT username, role, display_name, created_at FROM app_user ORDER BY username"
        ).fetchall()
    return [
        {**dict(r), "role_text": auth.ROLE_TEXT.get(r["role"], r["role"])}
        for r in rows
    ]

class UserIn(BaseModel):
    username: str
    password: str
    role: str = "member"
    display_name: str | None = None

class PasswordIn(BaseModel):
    new_password: str
    old_password: str | None = None

@router.post("/api/users/{username}/password")
def change_password(
    username: str,
    body: PasswordIn,
    actor: str = Depends(auth.current_user),
) -> dict[str, Any]:
    if len(body.new_password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    role = auth.role_of(actor)
    if actor != username and role != "admin":
        raise HTTPException(403, "只能修改自己的密码")

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM app_user WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "用户不存在")
        if actor == username and auth.AUTH_ENABLED:
            if not body.old_password or not auth.verify_password(
                body.old_password, row["password_hash"]
            ):
                raise HTTPException(403, "原密码错误")
        conn.execute(
            "UPDATE app_user SET password_hash = ? WHERE username = ?",
            (auth.hash_password(body.new_password), username),
        )
    return {"ok": True, "username": username}

class RoleIn(BaseModel):
    role: str

@router.patch("/api/users/{username}")
def set_role(
    username: str, body: RoleIn, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    if auth.role_of(actor) != "admin":
        raise HTTPException(403, "仅管理员可调整角色")
    if body.role not in ("admin", "manager", "member"):
        raise HTTPException(400, "role 只能是 admin/manager/member")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT username FROM app_user WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "用户不存在")
        conn.execute(
            "UPDATE app_user SET role = ? WHERE username = ?", (body.role, username)
        )
    return {"username": username, "role": body.role}

@router.post("/api/users")
def create_user(
    body: UserIn,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    if body.role not in ("admin", "manager", "member"):
        raise HTTPException(400, "role 只能是 admin/manager/member")
    with db.get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM app_user WHERE username = ?", (body.username,)
        ).fetchone()
        if exists:
            raise HTTPException(409, "user exists")
        conn.execute(
            "INSERT INTO app_user (username, password_hash, role, display_name, created_at)"
            " VALUES (?,?,?,?,?)",
            (
                body.username, auth.hash_password(body.password), body.role,
                body.display_name or body.username, db.now_iso(),
            ),
        )
    return {"username": body.username, "role": body.role}

# ---------------- 指标 ----------------

@router.get("/api/metrics")
def model_metrics(
    hours: int = 24,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return metrics.summary(conn, hours)
