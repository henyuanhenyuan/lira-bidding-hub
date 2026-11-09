from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, collect_logs, collect_tasks, collector, db, settings_store
from ..channels import _ADAPTERS

router = APIRouter()

CRAWL_CHANNELS = ("yingren", "native")


class CrawlRunIn(BaseModel):
    channel: str = "yingren"
    target_ids: list[str] = Field(default_factory=list)
    interval_s: int = Field(default=0, ge=0)
    priority: int = 0
    dispatch_now: bool = True


class CrawlConfigIn(BaseModel):
    yingren_base_url: str | None = None
    yingren_token: str | None = None
    native_crawler_url: str | None = None
    native_crawler_token: str | None = None


@router.get("/api/crawl/channels")
def crawl_channels(
    actor: str = Depends(auth.require_role("admin", "manager", "member", "viewer")),
) -> dict[str, Any]:
    view = settings_store.public_view()["sources"]
    return {
        "items": [
            {
                "channel": channel,
                "available": channel in _ADAPTERS,
                "configured": bool(
                    view.get(channel, {}).get("base_url")
                    and view.get(channel, {}).get("has_token")
                ),
                "detail": view.get(channel, {}),
            }
            for channel in CRAWL_CHANNELS
        ]
    }


@router.post("/api/crawl/config")
def crawl_config(
    body: CrawlConfigIn,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if values:
        settings_store.save(values)
    return crawl_channels(actor)


@router.post("/api/crawl/run")
def crawl_run(
    body: CrawlRunIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    if body.channel not in CRAWL_CHANNELS:
        raise HTTPException(400, f"不支持的采集通道：{body.channel}")
    created: list[str] = []
    with db.get_db() as conn:
        for target_id in body.target_ids:
            exists = conn.execute(
                "SELECT id FROM target WHERE id = ?", (target_id,)
            ).fetchone()
            if not exists:
                continue
            created.append(
                collect_tasks.create(
                    conn, target_id=target_id, channel=body.channel,
                    priority=body.priority, interval_s=body.interval_s,
                )
            )
    dispatched = (
        collector.dispatch_due(body.channel, limit=max(len(created), 5))
        if body.dispatch_now and created
        else {}
    )
    return {"created": created, "dispatch": dispatched}


@router.get("/api/crawl/logs")
def crawl_logs(
    limit: int = 100,
    actor: str = Depends(auth.require_role("admin", "manager", "member", "viewer")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"items": collect_logs.recent(conn, limit=limit)}
