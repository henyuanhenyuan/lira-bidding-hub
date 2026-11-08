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


# ---------------- 事件 ----------------

@router.get("/api/events")
def list_events(
    severity: str | None = None,
    target_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT e.*, t.title AS target_title, t.my_price AS my_price"
        " FROM event e LEFT JOIN target t ON t.id = e.target_id"
        " WHERE e.suppressed = 0"
    )
    params: list[Any] = []
    if severity:
        sql += " AND e.severity = ?"
        params.append(severity)
    if target_id:
        sql += " AND e.target_id = ?"
        params.append(target_id)
    sql += " ORDER BY e.ts DESC LIMIT ?"
    params.append(limit)
    with db.get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {**dict(r), "evidence": db.loads(r["evidence"], [])}
        for r in rows
    ]

@router.get("/api/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT e.*, t.title AS target_title, t.my_price AS my_price"
            " FROM event e LEFT JOIN target t ON t.id = e.target_id WHERE e.id = ?",
            (event_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "event not found")
        sugg = conn.execute(
            "SELECT * FROM suggestion WHERE event_id = ? ORDER BY created_at DESC LIMIT 1",
            (event_id,),
        ).fetchone()
        similar: list[dict[str, Any]] = []
        if sugg:
            ids = db.loads(sugg["case_ids"], [])
            if ids:
                marks = ",".join("?" * len(ids))
                rows_ = conn.execute(
                    f"SELECT id, summary, attribution, outcome_7d, price_band, delta_pct"
                    f' FROM "case" WHERE id IN ({marks})',
                    ids,
                ).fetchall()
                by_id = {r["id"]: dict(r) for r in rows_}
                similar = [by_id[i] for i in ids if i in by_id]
    return {
        **dict(row),
        "evidence": db.loads(row["evidence"], []),
        "suggestion": (
            {**dict(sugg), "case_ids": db.loads(sugg["case_ids"], [])}
            if sugg else None
        ),
        "similar_cases": similar,
    }

# ---------------- 分析与建议 ----------------

@router.post("/api/events/{event_id}/analyze")
def analyze_event(event_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM event WHERE id = ?", (event_id,)
        ).fetchone()
    if not exists:
        raise HTTPException(404, "event not found")
    if gates.ENFORCE:
        with db.get_db() as conn:
            state = gates.status(conn)
        if not state["ok"]:
            raise HTTPException(
                423, "上线门禁未通过：" + "；".join(state["reasons"])
            )
    try:
        return agent_graph.run_for_event(event_id, trigger="api")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get("/api/agent/runs")
def list_agent_runs(
    event_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    sql = (
        "SELECT r.*, e.type AS event_type, e.severity, t.title AS target_title"
        " FROM agent_run r"
        " LEFT JOIN event e ON e.id = r.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
    )
    params: list[Any] = []
    if event_id:
        sql += " WHERE r.event_id = ?"
        params.append(event_id)
    sql += " ORDER BY r.started_at DESC LIMIT ?"
    params.append(max(1, min(200, limit)))
    with db.get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {**dict(row), "plan": db.loads(row["plan"], [])}
        for row in rows
    ]

@router.get("/api/agent/runs/{run_id}")
def get_agent_run(run_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        run = conn.execute(
            "SELECT * FROM agent_run WHERE id = ?", (run_id,)
        ).fetchone()
        if not run:
            raise HTTPException(404, "agent run not found")
        steps = conn.execute(
            "SELECT * FROM agent_step WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
    return {
        **dict(run),
        "plan": db.loads(run["plan"], []),
        "steps": [
            {**dict(step), "input": _payload(step["input"]), "output": _payload(step["output"])}
            for step in steps
        ],
    }
