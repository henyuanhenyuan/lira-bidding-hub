from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import agent_graph, auth, autopilot, db, settings_store

router = APIRouter()


class ResolveIn(BaseModel):
    approve: bool = True
    note: str | None = None
    executed_price: float | None = Field(default=None, gt=0)


class AutopilotConfigIn(BaseModel):
    enabled: bool | None = None
    strategy: str | None = None
    undercut_pct: float | None = Field(default=None, ge=0, le=0.5)
    max_delta_pct: float | None = Field(default=None, gt=0, le=1)
    min_confidence: float | None = Field(default=None, ge=0, le=1)


@router.get("/api/autopilot/status")
def autopilot_status(
    actor: str = Depends(auth.require_role("admin", "manager", "member", "viewer")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return autopilot.status(conn)


@router.get("/api/autopilot/exceptions")
def autopilot_exceptions(
    limit: int = 100,
    actor: str = Depends(auth.require_role("admin", "manager", "member", "viewer")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"items": autopilot.exceptions(conn, limit=limit)}


@router.post("/api/autopilot/exceptions/{suggestion_id}/resolve")
def resolve_exception(
    suggestion_id: str,
    body: ResolveIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            result = autopilot.resolve_exception(
                conn, suggestion_id, actor, auth.role_of(actor),
                approve=body.approve, note=body.note,
                executed_price=body.executed_price,
            )
        except KeyError:
            raise HTTPException(404, "建议不存在")
        except Exception as exc:
            raise HTTPException(400, str(exc))
    return result


@router.get("/api/autopilot/ledger")
def bid_ledger(
    region: str | None = None,
    limit: int = 100,
    actor: str = Depends(auth.require_role("admin", "manager", "member", "viewer")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"items": autopilot.ledger(conn, region=region, limit=limit)}


@router.get("/api/regions")
def region_list(
    actor: str = Depends(auth.require_role("admin", "manager", "member", "viewer")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"items": autopilot.regions(conn)}


@router.post("/api/autopilot/config")
def set_autopilot_config(
    body: AutopilotConfigIn,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    settings_store.save(values)
    return autopilot.config()


@router.post("/api/autopilot/run/{target_id}")
def run_for_target(
    target_id: str,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    """手动触发某个目标最近事件的一次自主研判。"""
    with db.get_db() as conn:
        event = conn.execute(
            "SELECT e.id FROM event e"
            " LEFT JOIN suggestion s ON s.event_id = e.id"
            " WHERE e.target_id = ? AND e.suppressed = 0 AND s.id IS NULL"
            " ORDER BY e.ts DESC LIMIT 1",
            (target_id,),
        ).fetchone()
    if not event:
        raise HTTPException(404, "该目标没有待研判事件")
    return agent_graph.run_for_event(event["id"], trigger="autopilot_manual")


@router.post("/api/autopilot/tick")
def autopilot_tick(
    limit: int = 20,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    from .. import scheduler

    return {"ran": scheduler.run_autopilot(limit=limit)}
