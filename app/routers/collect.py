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


# ---------------- 采集运维 ----------------

class CollectTaskIn(BaseModel):
    target_id: str
    channel: str = "rpa"
    interval_s: int = 0
    priority: int = 0
    max_attempts: int = 3

@router.get("/api/collect/tasks")
def collect_task_list(
    channel: str | None = None,
    limit: int = 200,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"tasks": collect_tasks.list_tasks(conn, channel=channel, limit=limit)}

@router.post("/api/collect/tasks")
def collect_task_create(
    body: CollectTaskIn,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            task_id = collect_tasks.create(
                conn, target_id=body.target_id, channel=body.channel,
                priority=body.priority, max_attempts=body.max_attempts,
                interval_s=body.interval_s,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return collect_tasks.get(conn, task_id)

@router.delete("/api/collect/tasks/{task_id}")
def collect_task_cancel(
    task_id: str,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        if not collect_tasks.cancel(conn, task_id):
            raise HTTPException(404, "task not found")
    return {"id": task_id, "status": "cancelled"}

@router.get("/api/collect/logs")
def collect_log_list(
    limit: int = 100,
    channel: str | None = None,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"logs": collect_logs.recent(conn, limit=limit, channel=channel)}

@router.get("/api/collect/summary")
def collect_log_summary(
    hours: int = 24,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return collect_logs.summary(conn, hours=hours)

@router.get("/api/collect/reviews")
def collect_review_list(
    limit: int = 100,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return {"reviews": review_queue.pending(conn, limit=limit)}

@router.post("/api/collect/reviews/{review_id}/resolve")
def collect_review_resolve(
    review_id: str,
    decision: str,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            status = review_queue.resolve(conn, review_id, decision, actor)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if status is None:
        raise HTTPException(404, "review not found")
    return {"id": review_id, "status": status}
