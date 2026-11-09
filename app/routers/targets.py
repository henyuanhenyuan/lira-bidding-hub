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


class TargetPatch(BaseModel):
    my_sku: str | None = None
    my_price: float | None = None
    title: str | None = None
    holdout: bool | None = None
    region: str | None = None
    pricing_strategy: str | None = None
    url: str | None = None
    price_selector: str | None = None

@router.get("/api/targets/{target_id}")
def get_target(target_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM target WHERE id = ?", (target_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "target not found")
    return dict(row)

@router.patch("/api/targets/{target_id}")
def patch_target(target_id: str, patch: TargetPatch) -> dict[str, Any]:
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "holdout" in fields:
        fields["holdout"] = int(bool(fields["holdout"]))
    if not fields:
        raise HTTPException(400, "nothing to update")
    sets = ", ".join(f"{k} = ?" for k in fields)
    with db.get_db() as conn:
        conn.execute(f"UPDATE target SET {sets} WHERE id = ?", (*fields.values(), target_id))
        row = conn.execute("SELECT * FROM target WHERE id = ?", (target_id,)).fetchone()
    if not row:
        raise HTTPException(404, "target not found")
    return dict(row)

@router.get("/api/targets/{target_id}/prices")
def price_series(target_id: str, limit: int = 60) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT ts, price_low, price_high, confidence, missing_fields"
            " FROM price_point WHERE target_id = ? ORDER BY ts DESC LIMIT ?",
            (target_id, limit),
        ).fetchall()
    return [
        {**dict(r), "missing_fields": db.loads(r["missing_fields"], [])}
        for r in reversed(rows)
    ]
