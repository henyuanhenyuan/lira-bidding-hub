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


# ---------------- 自然语言问数 ----------------

class AskIn(BaseModel):
    question: str

@router.get("/api/ask/templates")
def ask_templates() -> list[dict[str, Any]]:
    return nlq.templates_info()

@router.post("/api/ask")
def ask(body: AskIn) -> dict[str, Any]:
    with db.get_db() as conn:
        return nlq.ask(conn, body.question)

# ---------------- 评论与洞察 ----------------

class ReviewIn(BaseModel):
    ts: str | None = None
    rating: int | None = None
    content: str

class ReviewsIn(BaseModel):
    target_id: str
    reviews: list[ReviewIn]

@router.post("/api/reviews")
def add_reviews(body: ReviewsIn) -> dict[str, Any]:
    with db.get_db() as conn:
        result = review_store.add_reviews(
            conn, body.target_id, [r.model_dump() for r in body.reviews]
        )
    return result

@router.get("/api/reviews")
def list_reviews(target_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return review_store.list_reviews(conn, target_id, limit)

@router.post("/api/reviews/seed")
def seed_reviews(target_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        return review_store.seed(conn, target_id)

@router.post("/api/targets/{target_id}/insights")
def run_insight(target_id: str, window_days: int = 7) -> dict[str, Any]:
    with db.get_db() as conn:
        insight = review_store.analyze(conn, target_id, window_days)
    if insight is None:
        raise HTTPException(404, "该目标在窗口内没有评论")
    return insight

@router.get("/api/targets/{target_id}/insights")
def get_insight(target_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        insight = review_store.latest_insight(conn, target_id)
    if insight is None:
        raise HTTPException(404, "尚无洞察")
    return insight
