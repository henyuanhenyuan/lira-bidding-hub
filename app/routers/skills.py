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


@router.get("/api/skills")
def list_skills() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return skills.list_skills(conn)

class SkillIn(BaseModel):
    name: str
    playbook: str
    event_types: list[str] = []
    allowed_tools: list[str] = []
    description: str | None = None
    min_severity: str = "L1"
    enabled: bool = True
    stages: list[str] | None = None
    output_schema: dict[str, Any] | None = None

@router.post("/api/skills")
def create_skill(
    body: SkillIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            return skills.create_skill(
                conn,
                name=body.name,
                playbook=body.playbook,
                event_types=body.event_types,
                allowed_tools=body.allowed_tools or list(skills.ALL_TOOLS),
                description=body.description,
                min_severity=body.min_severity,
                enabled=body.enabled,
                stages=body.stages,
                output_schema=body.output_schema,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

class SkillPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    event_types: list[str] | None = None
    min_severity: str | None = None
    playbook: str | None = None
    allowed_tools: list[str] | None = None
    enabled: bool | None = None
    stages: list[str] | None = None
    output_schema: dict[str, Any] | None = None

@router.patch("/api/skills/{skill_id}")
def patch_skill(
    skill_id: str,
    body: SkillPatch,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        try:
            return skills.update_skill(
                conn, skill_id, body.model_dump(exclude_none=True)
            )
        except KeyError as exc:
            raise HTTPException(404, "skill not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

@router.post("/api/skills/{skill_id}/validate")
def validate_skill(
    skill_id: str,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT playbook FROM skill WHERE id = ?", (skill_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "skill not found")
    return skills.validate_playbook(row["playbook"])
