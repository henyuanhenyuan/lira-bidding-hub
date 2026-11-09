from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, db, ingest, settings_store
from ..contracts import SnapshotIn

router = APIRouter()

SCOPES = ("ingest", "read")
ENDPOINTS = [
    {
        "name": "推送快照",
        "method": "POST",
        "path": "/v1/ingest/snapshots",
        "auth": "Bearer <接入令牌>",
        "description": "采集端把原始观测推进来，服务端统一算到手价、去重并生成事件。",
    },
    {
        "name": "干跑校验",
        "method": "POST",
        "path": "/v1/ingest/validate",
        "auth": "Bearer <接入令牌>",
        "description": "只校验契约不落库，给爬虫/脚本自查用。",
    },
    {
        "name": "文件导入",
        "method": "POST",
        "path": "/api/import/file",
        "auth": "登录 Cookie",
        "description": "CSV 或 JSON 快照文件，适合历史数据回填。",
    },
    {
        "name": "健康检查",
        "method": "GET",
        "path": "/api/health",
        "auth": "公开",
        "description": "目标、快照、事件、建议与向量索引的计数。",
    },
]


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    scopes: list[str] = ["ingest"]


@router.get("/api/integration/overview")
def overview(actor: str = Depends(auth.require_role("admin", "manager"))) -> dict[str, Any]:
    window = "-1 day"
    with db.get_db() as conn:
        active = conn.execute(
            "SELECT COUNT(*) c FROM api_token WHERE revoked_at IS NULL"
        ).fetchone()["c"]
        total = conn.execute("SELECT COUNT(*) c FROM api_token").fetchone()["c"]
        last = conn.execute(
            "SELECT * FROM ingest_log ORDER BY received_at DESC LIMIT 1"
        ).fetchone()
        sources = conn.execute(
            "SELECT source, COUNT(*) batches, COALESCE(SUM(rows_ok), 0) rows_ok,"
            " COALESCE(SUM(rows_dup), 0) rows_dup, MAX(received_at) last_at"
            " FROM ingest_log WHERE datetime(received_at) >= datetime('now', ?)"
            " GROUP BY source ORDER BY rows_ok DESC",
            (window,),
        ).fetchall()
        counts = {
            "targets": conn.execute("SELECT COUNT(*) c FROM target").fetchone()["c"],
            "snapshots": conn.execute("SELECT COUNT(*) c FROM snapshot").fetchone()["c"],
            "events": conn.execute("SELECT COUNT(*) c FROM event").fetchone()["c"],
        }
    models = settings_store.public_view()
    return {
        "endpoints": ENDPOINTS,
        "tokens": {"active": active, "total": total},
        "counts": counts,
        "ingest": {
            "last": dict(last) if last else None,
            "sources": [dict(row) for row in sources],
        },
        "model": {
            "core": models["api"]["model"],
            "core_ready": models["api"]["has_key"],
            "test": models["local"]["model"],
            "route": models["route"],
        },
        "sample": {
            "snapshots": [
                {
                    "target_id": "demo-sku-001",
                    "ts": db.now_iso(),
                    "collector": "integration-console",
                    "source_tier": 2,
                    "observation": {
                        "list_price": 259.0,
                        "title": "演示竞品 · 控油洗发水",
                        "account_tier": "normal",
                    },
                }
            ]
        },
    }


@router.get("/api/integration/tokens")
def list_tokens(actor: str = Depends(auth.require_role("admin", "manager"))) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, prefix, scopes, created_by, created_at,"
            " last_used_at, call_count, revoked_at FROM api_token"
            " ORDER BY created_at DESC"
        ).fetchall()
    return [
        {**dict(row), "scopes": db.loads(row["scopes"], [])}
        for row in rows
    ]


@router.post("/api/integration/tokens")
def create_token(
    body: TokenIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    scopes = [scope for scope in body.scopes if scope in SCOPES] or ["ingest"]
    raw = f"lm_{secrets.token_hex(4)}.{secrets.token_urlsafe(24)}"
    token_id = db.new_id()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO api_token (id, name, prefix, token_hash, scopes,"
            " created_by, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                token_id, body.name.strip(), raw[:14], _token_hash(raw),
                json.dumps(scopes), actor, db.now_iso(),
            ),
        )
    return {
        "id": token_id,
        "name": body.name.strip(),
        "prefix": raw[:14],
        "token": raw,
        "scopes": scopes,
        "note": "令牌只显示这一次，请立刻保存。",
    }


@router.delete("/api/integration/tokens/{token_id}")
def revoke_token(
    token_id: str,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM api_token WHERE id = ?", (token_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "令牌不存在")
        conn.execute(
            "UPDATE api_token SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (db.now_iso(), token_id),
        )
    return {"ok": True, "id": token_id}


@router.get("/api/integration/logs")
def ingest_logs(
    limit: int = 20,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, source, file_name, rows_in, rows_ok, rows_dup,"
            " rows_rejected, errors, received_at FROM ingest_log"
            " ORDER BY received_at DESC LIMIT ?",
            (max(1, min(100, limit)),),
        ).fetchall()
    return [
        {**dict(row), "errors": db.loads(row["errors"], [])}
        for row in rows
    ]


class TestPushIn(BaseModel):
    target_id: str = "demo-sku-001"
    title: str = "演示竞品 · 控油洗发水"
    price: float = Field(default=259.0, ge=0)
    source_tier: int = Field(default=2, ge=0, le=4)
    collector: str = "integration-console"


@router.post("/api/integration/test-push")
def test_push(
    body: TestPushIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    """用真实摄取链路发一条演示快照，验证从接入到事件的完整闭环。"""
    snapshot = SnapshotIn(
        target_id=body.target_id.strip() or "demo-sku-001",
        ts=db.now_iso(),
        collector=body.collector.strip() or "integration-console",
        source_tier=body.source_tier,  # type: ignore[arg-type]
        observation={"list_price": body.price, "title": body.title},
    )
    with db.get_db() as conn:
        report = ingest.ingest(conn, [snapshot], source="console")
    return {"ok": report.rows_ok > 0, **report.as_dict()}
