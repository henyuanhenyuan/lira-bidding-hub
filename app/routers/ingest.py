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
    config, connectors, csvimport, db, docs as doc_store, eval as eval_store,
    executor, gates, guardrail, ingest, inbox, metrics, nlq, notify,
    review_queue, reviews as review_store, scheduler, skills, stream, tracing,
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


# ---------------- 采集 ----------------

@router.post("/v1/ingest/snapshots")
def ingest_snapshots(batch: IngestBatch) -> dict[str, Any]:
    with db.get_db() as conn:
        report = ingest.ingest(conn, batch.snapshots, source="api", file_name=batch.file_name)
    return report.as_dict()

MAX_UPLOAD = 50 * 1024 * 1024

@router.post("/v1/ingest/validate")
def validate_batch(batch: IngestBatch) -> dict[str, Any]:
    """干跑：只校验契约，不落库。给采集端自查用。"""
    errors: list[dict[str, Any]] = []
    for i, s in enumerate(batch.snapshots):
        if s.observation.list_price is None:
            errors.append({"index": i, "target_id": s.target_id,
                           "error": "list_price is required"})
    return {
        "ok": not errors,
        "rows": len(batch.snapshots),
        "errors": errors,
    }

@router.post("/v1/import/validate")
async def validate_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (max 50MB)")
    snaps, errors = csvimport.parse_csv_bytes(raw)
    for i, s in enumerate(snaps):
        if s.observation.list_price is None:
            errors.append({"line": i + 2, "error": "list_price 为空，无法计算到手价"})
    return {"ok": not errors, "rows": len(snaps), "errors": errors}


@router.post("/v1/import/csv")
async def import_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (max 50MB)")
    snaps, parse_errors = csvimport.parse_csv_bytes(raw)

    with db.get_db() as conn:
        report = ingest.ingest(conn, snaps, source="csv", file_name=file.filename)

    out = report.as_dict()
    out["errors"] = parse_errors + out["errors"]
    out["rows_rejected"] += len(parse_errors)
    return out


# ---------------- 目标 ----------------

@router.get("/api/targets")
def list_targets() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, platform, title, my_sku, my_price, active, mapping_status, holdout"
            " FROM target ORDER BY title"
        ).fetchall()
    return [dict(r) for r in rows]
