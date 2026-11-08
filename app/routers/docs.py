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


@router.get("/api/docs")
def list_docs() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return doc_store.list_docs(conn)

class DocIn(BaseModel):
    title: str
    content: str
    source: str | None = None
    category: str | None = None
    version: str | None = None

@router.post("/api/docs")
def create_doc(
    body: DocIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    if not body.title.strip() or not body.content.strip():
        raise HTTPException(400, "标题和内容不能为空")
    with db.get_db() as conn:
        try:
            return doc_store.create_doc(
                conn,
                title=body.title.strip(),
                content=body.content,
                source=body.source,
                category=body.category,
                version=body.version,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

@router.get("/api/docs/{doc_id}")
def get_doc(doc_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        doc = doc_store.get_doc(conn, doc_id)
    if not doc:
        raise HTTPException(404, "doc not found")
    return doc

@router.get("/api/doc-chunks/{chunk_id}")
def get_doc_chunk(chunk_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        chunk = doc_store.get_chunk(conn, chunk_id)
    if not chunk:
        raise HTTPException(404, "chunk not found")
    return chunk
