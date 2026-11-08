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


@router.get("/api/eval/cases")
def eval_cases() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return eval_store.list_cases(conn)

@router.post("/api/eval/run")
def run_eval(
    limit: int | None = None,
    tier: str | None = None,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    if tier:
        return eval_runner.run(tier=tier, limit=limit)
    return eval_store.run(limit)

@router.get("/api/eval/runs")
def eval_runs(limit: int = 20) -> list[dict[str, Any]]:
    return eval_runner.list_runs(limit)

@router.get("/api/eval/badcases")
def eval_badcases(run_key: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return eval_runner.list_badcases(run_key, limit)

@router.get("/api/eval/runs/{run_key}/report")
def eval_report_md(run_key: str) -> Response:
    run = next(
        (item for item in eval_runner.list_runs(200) if item["run_key"] == run_key),
        None,
    )
    if run is None:
        raise HTTPException(404, "评测记录不存在")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT results FROM eval_run WHERE run_key = ?", (run_key,)
        ).fetchone()
    results = json.loads(row["results"]) if row and row["results"] else []
    text = eval_report.render(
        {"run_key": run_key, "tier": run.get("tier"), "metrics": run.get("metrics"),
         "results": results}
    )
    return Response(content=text, media_type="text/markdown; charset=utf-8")

@router.get("/api/observability/traces")
def trace_list(run_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    sql = "SELECT trace_id, COUNT(*) AS spans, MIN(started_at) AS started_at"
    sql += " FROM span"
    params: list[Any] = []
    if run_id:
        sql += " WHERE run_id = ?"
        params.append(run_id)
    sql += " GROUP BY trace_id ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

@router.get("/api/observability/traces/{trace_id}")
def trace_detail(trace_id: str) -> dict[str, Any]:
    return tracing.list_trace(trace_id)
