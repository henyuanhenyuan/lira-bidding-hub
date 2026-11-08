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


@router.get("/api/suggestions/{sid}/risk")
def suggestion_risk(sid: str) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (sid,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "建议不存在")
    risk = approval.assess_risk(row)
    return {**risk, "roles": list(risk["roles"])}

@router.get("/api/suggestions/{sid}")
def get_suggestion(sid: str) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (sid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "suggestion not found")
        event = conn.execute(
            "SELECT e.*, t.title AS target_title, t.my_price AS my_price"
            " FROM event e LEFT JOIN target t ON t.id = e.target_id"
            " WHERE e.id = ?",
            (row["event_id"],),
        ).fetchone()
        evidence = db.loads(event["evidence"], []) if event else []
        doc_ids = list(
            dict.fromkeys(
                item.split(":", 1)[1]
                for item in evidence
                if item.startswith("doc:")
            )
        )
        evidence_docs: list[dict[str, Any]] = []
        if doc_ids:
            marks = ", ".join("?" for _ in doc_ids)
            evidence_docs = [
                dict(item)
                for item in conn.execute(
                    "SELECT c.id, c.doc_id, c.chunk_no, c.content,"
                    " d.title AS doc_title"
                    " FROM doc_chunk c JOIN doc d ON d.id = c.doc_id"
                    f" WHERE c.id IN ({marks})",
                    doc_ids,
                ).fetchall()
            ]
    result = dict(row)
    result["case_ids"] = db.loads(row["case_ids"], [])
    result["evidence_docs"] = evidence_docs
    if event:
        event_dict = dict(event)
        event_dict["evidence"] = evidence
        result["event"] = event_dict
    else:
        result["event"] = None
    return result

@router.get("/api/suggestions")
def list_suggestions(limit: int = 50) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT s.*, e.target_id, e.type AS event_type, t.title AS target_title"
            " FROM suggestion s"
            " LEFT JOIN event e ON e.id = s.event_id"
            " LEFT JOIN target t ON t.id = e.target_id"
            " ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]

class ApprovalAction(BaseModel):
    note: str | None = None

class ExecuteIn(BaseModel):
    executed_price: float | None = None
    note: str | None = None

def _transition(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        with db.get_db() as conn:
            result = fn(conn, *args, **kwargs)
    except approval.TransitionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "suggestion not found") from exc
    stream.publish("approval", {
        "id": result.get("id"), "status": result.get("status"),
    })
    return result

@router.post("/api/suggestions/{sid}/submit")
def submit_suggestion(
    sid: str, body: ApprovalAction, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    return _transition(approval.submit, sid, actor, auth.role_of(actor), body.note)

@router.post("/api/suggestions/{sid}/approve")
def approve_suggestion(
    sid: str, body: ApprovalAction, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    return _transition(approval.approve, sid, actor, auth.role_of(actor), body.note)

@router.post("/api/suggestions/{sid}/reject")
def reject_suggestion(
    sid: str, body: ApprovalAction, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    return _transition(approval.reject, sid, actor, auth.role_of(actor), body.note)

@router.post("/api/suggestions/{sid}/execute")
def execute_suggestion(
    sid: str, body: ExecuteIn, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    role = auth.role_of(actor)
    try:
        execution = executor.run(sid, actor, role, body.executed_price, body.note)
    except KeyError as exc:
        raise HTTPException(404, "suggestion not found") from exc
    except executor.ExecutorError as exc:
        raise HTTPException(400, str(exc)) from exc

    if execution.get("idempotent"):
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM suggestion WHERE id = ?", (sid,)
            ).fetchone()
        return {**dict(row), "execution": execution}

    result = _transition(
        approval.execute, sid, actor, role,
        execution["plan"]["to_price"], body.note,
    )
    with db.get_db() as conn:
        conn.execute(
            "UPDATE suggestion SET execution_id = ? WHERE id = ?",
            (execution["id"], sid),
        )
    return {**result, "execution": execution}

@router.get("/api/suggestions/{sid}/execution-preview")
def execution_preview(sid: str) -> dict[str, Any]:
    try:
        return executor.preview(sid)
    except KeyError as exc:
        raise HTTPException(404, "suggestion not found") from exc
    except executor.ExecutorError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.get("/api/suggestions/{sid}/executions")
def suggestion_executions(sid: str) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return executor.history(conn, sid)

@router.post("/api/executions/{execution_id}/rollback")
def rollback_execution(
    execution_id: str,
    actor: str = Depends(auth.current_user),
) -> dict[str, Any]:
    try:
        return executor.rollback(execution_id, actor, auth.role_of(actor))
    except KeyError as exc:
        raise HTTPException(404, "execution not found") from exc
    except (executor.ExecutorError, approval.TransitionError) as exc:
        raise HTTPException(400, str(exc)) from exc

@router.post("/api/suggestions/{sid}/cancel")
def cancel_suggestion(
    sid: str, body: ApprovalAction, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    return _transition(approval.cancel, sid, actor, auth.role_of(actor), body.note)

@router.get("/api/suggestions/{sid}/timeline")
def suggestion_timeline(sid: str) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return approval.timeline(conn, sid)

@router.get("/api/approvals/inbox")
def approvals_inbox() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return approval.inbox(conn)

class OutcomeIn(BaseModel):
    result: str
    note: str | None = None
    sales_delta: float | None = None

@router.post("/api/suggestions/{suggestion_id}/outcome")
def record_outcome(
    suggestion_id: str,
    body: OutcomeIn,
    actor: str = Depends(auth.current_user),
) -> dict[str, Any]:
    try:
        with db.get_db() as conn:
            return outcome_store.record(
                conn, suggestion_id, body.result, body.note, body.sales_delta, actor
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "suggestion not found") from exc

@router.get("/api/suggestions/{suggestion_id}/outcome")
def get_outcome(suggestion_id: str) -> dict[str, Any] | None:
    with db.get_db() as conn:
        return outcome_store.get(conn, suggestion_id)

@router.get("/api/outcomes/due")
def due_outcomes(days: int = 7) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return outcome_store.due_list(conn, days)

@router.get("/api/gates")
def gate_status() -> dict[str, Any]:
    with db.get_db() as conn:
        return gates.status(conn)

@router.get("/api/outcomes/overdue")
def overdue_outcomes(days: int = 7) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return outcome_store.overdue(conn, days)
