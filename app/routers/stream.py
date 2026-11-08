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


@router.get("/api/stream")
def event_stream() -> StreamingResponse:
    q = stream.subscribe()

    def gen():
        try:
            yield ": connected\nretry: 3000\n\n"
            while True:
                try:
                    payload = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield stream.format_sse(payload)
        finally:
            stream.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.get("/api/events/{event_id}/analyze/stream")
def analyze_stream(event_id: str) -> StreamingResponse:
    """研判进度流：start → suggestion → narrative 分片 → done。"""

    def gen():
        yield _sse("start", {"event_id": event_id})
        try:
            result = agent_graph.run_for_event(event_id, trigger="api:stream")
        except Exception as exc:  # 事件不存在等
            yield _sse("error", {"detail": str(exc)})
            return
        yield _sse(
            "suggestion",
            {
                "id": result.get("id"), "action": result.get("action"),
                "confidence": result.get("confidence"),
                "guardrail": result.get("guardrail"),
            },
        )
        narrative = str(result.get("narrative") or "")
        for index in range(0, len(narrative), 24):
            yield _sse("narrative", {"text": narrative[index:index + 24]})
        yield _sse("done", {"narrative": narrative})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post("/api/llm/stream")
def llm_stream(
    body: dict[str, Any],
    actor: str = Depends(auth.require_role("admin")),
) -> StreamingResponse:
    """调试用：直接把网关的 token 流透出，验证多 Provider 流式能力。"""
    messages = body.get("messages") or [
        {"role": "user", "content": str(body.get("prompt") or "")},
    ]

    def gen():
        for piece in llm.stream(messages, kind="analysis", max_tokens=256):
            yield _sse("token", {"text": piece})
        yield _sse("done", {})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
