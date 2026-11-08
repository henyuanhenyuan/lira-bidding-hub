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


# ---------------- 案例库 ----------------

class CaseIn(BaseModel):
    category: str
    event_type: str
    summary: str
    attribution: str
    price_band: str
    delta_pct: float | None = None
    decision: str | None = None
    outcome_7d: str | None = None
    ts: str | None = None

@router.post("/api/cases")
def add_case(body: CaseIn) -> dict[str, Any]:
    with db.get_db() as conn:
        cid = case_store.create(conn, **body.model_dump())
        row = conn.execute(
            'SELECT id, category, event_type, price_band, summary FROM "case" WHERE id = ?',
            (cid,),
        ).fetchone()
    return dict(row)

@router.get("/api/cases")
def list_cases(limit: int = 100) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, event_type, price_band, delta_pct, summary, attribution,"
            ' decision, outcome_7d, ts, embed_provider FROM "case" ORDER BY ts DESC LIMIT ?',
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]

@router.post("/api/cases/seed")
def seed_cases() -> dict[str, Any]:
    with db.get_db() as conn:
        added = case_store.seed(conn)
        total = case_store.count(conn)
    return {"added": added, "total": total}

@router.get("/api/cases/search")
def search_cases(
    q: str,
    event_type: str | None = None,
    price_band: str | None = None,
    delta_pct: float | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        found = case_store.search(
            conn, query=q, category=None, event_type=event_type,
            price_band=price_band, delta_pct=delta_pct, limit=limit,
        )
    return [c.as_dict() for c in found]
