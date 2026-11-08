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


# ---------------- 采集 ----------------

@router.post("/v1/ingest/snapshots")
def ingest_snapshots(batch: IngestBatch) -> dict[str, Any]:
    with db.get_db() as conn:
        report = ingest.ingest(conn, batch.snapshots, source="api", file_name=batch.file_name)
    return report.as_dict()


@router.post("/v1/ingest/validate")
def validate_batch(batch: IngestBatch) -> dict[str, Any]:
    """干跑：只校验契约，不落库。给采集端自查用。"""
    errors: list[dict[str, Any]] = []
    for index, snapshot in enumerate(batch.snapshots):
        if snapshot.observation.list_price is None:
            errors.append(
                {
                    "index": index,
                    "target_id": snapshot.target_id,
                    "error": "list_price is required",
                }
            )
    return {"ok": not errors, "rows": len(batch.snapshots), "errors": errors}


# ---------------- 目标 ----------------

@router.get("/api/targets")
def list_targets() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, platform, title, my_sku, my_price, active, mapping_status, holdout"
            " FROM target ORDER BY title"
        ).fetchall()
    return [dict(r) for r in rows]
