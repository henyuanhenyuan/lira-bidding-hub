from __future__ import annotations

import json
import queue
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import (
    agent, agent_graph, alignment, approval, auth, collectors, config, connectors,
    csvimport, db, docs as doc_store, eval as eval_store, executor, gates,
    guardrail, ingest, inbox, metrics, nlq, notify, reviews as review_store,
    scheduler, skills, stream,
)
from . import outcome as outcome_store
from . import cases as case_store
from .contracts import IngestBatch, PricePoint, SnapshotIn

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


class TargetPatch(BaseModel):
    my_sku: str | None = None
    my_price: float | None = None
    title: str | None = None
    holdout: bool | None = None


@router.get("/api/targets/{target_id}")
def get_target(target_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM target WHERE id = ?", (target_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "target not found")
    return dict(row)


@router.patch("/api/targets/{target_id}")
def patch_target(target_id: str, patch: TargetPatch) -> dict[str, Any]:
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "holdout" in fields:
        fields["holdout"] = int(bool(fields["holdout"]))
    if not fields:
        raise HTTPException(400, "nothing to update")
    sets = ", ".join(f"{k} = ?" for k in fields)
    with db.get_db() as conn:
        conn.execute(f"UPDATE target SET {sets} WHERE id = ?", (*fields.values(), target_id))
        row = conn.execute("SELECT * FROM target WHERE id = ?", (target_id,)).fetchone()
    if not row:
        raise HTTPException(404, "target not found")
    return dict(row)


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


@router.get("/api/targets/{target_id}/prices")
def price_series(target_id: str, limit: int = 60) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT ts, price_low, price_high, confidence, missing_fields"
            " FROM price_point WHERE target_id = ? ORDER BY ts DESC LIMIT ?",
            (target_id, limit),
        ).fetchall()
    return [
        {**dict(r), "missing_fields": db.loads(r["missing_fields"], [])}
        for r in reversed(rows)
    ]


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


def _payload(value: Any) -> Any:
    parsed = db.loads(value, None)
    return parsed if parsed is not None else value


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


@router.get("/api/eval/cases")
def eval_cases() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return eval_store.list_cases(conn)


@router.post("/api/eval/run")
def run_eval(
    limit: int | None = None,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    return eval_store.run(limit)


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


# ---------------- 我方商品与 SKU 对齐 ----------------

class ProductIn(BaseModel):
    sku: str
    title: str
    price: float | None = None
    cost: float | None = None
    margin_floor: float = 0.15
    category: str | None = None
    image_url: str | None = None


DEMO_PRODUCTS = [
    {"sku": "SKU-A", "title": "洗护套装 洗发水+护发素", "price": 289,
     "cost": 180, "margin_floor": 0.15, "category": "洗护"},
    {"sku": "SKU-B", "title": "控油洗发水 500ml", "price": 199,
     "cost": 150, "margin_floor": 0.15, "category": "洗护"},
    {"sku": "SKU-C", "title": "柔顺护发素 400ml", "price": 100,
     "cost": 88, "margin_floor": 0.15, "category": "洗护"},
]


@router.get("/api/my-products")
def list_products() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM my_product ORDER BY sku"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/my-products")
def add_product(body: ProductIn) -> dict[str, Any]:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO my_product (sku, title, price, cost, margin_floor,"
            " category, image_url, active) VALUES (?,?,?,?,?,?,?,1)"
            " ON CONFLICT (sku) DO UPDATE SET title=excluded.title, price=excluded.price,"
            " cost=excluded.cost, margin_floor=excluded.margin_floor,"
            " category=excluded.category, image_url=excluded.image_url,"
            " active=excluded.active",
            (body.sku, body.title, body.price, body.cost, body.margin_floor,
             body.category, body.image_url),
        )
    return body.model_dump()


@router.post("/api/my-products/seed")
def seed_products() -> dict[str, Any]:
    with db.get_db() as conn:
        for p in DEMO_PRODUCTS:
            exists = conn.execute(
                "SELECT 1 FROM my_product WHERE sku = ?", (p["sku"],)
            ).fetchone()
            if exists:
                # 已存在的老数据：只补齐成本与护栏，不覆盖用户改过的价格
                conn.execute(
                    "UPDATE my_product SET cost = COALESCE(cost, ?),"
                    " margin_floor = COALESCE(margin_floor, ?) WHERE sku = ?",
                    (p["cost"], p["margin_floor"], p["sku"]),
                )
            else:
                conn.execute(
                    "INSERT INTO my_product (sku, title, price, cost, margin_floor,"
                    " category, active) VALUES (?,?,?,?,?,?,1)",
                    (p["sku"], p["title"], p["price"], p["cost"],
                     p["margin_floor"], p["category"]),
                )
        total = conn.execute("SELECT COUNT(*) c FROM my_product").fetchone()["c"]
    return {"total": total}


@router.get("/api/mappings")
def get_mappings(status: str | None = None) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        return alignment.list_mappings(conn, status)


@router.post("/api/mappings/suggest")
def suggest_mappings() -> dict[str, Any]:
    with db.get_db() as conn:
        created = alignment.auto_suggest(conn)
        total = conn.execute(
            "SELECT COUNT(*) c FROM mapping WHERE status = 'pending'"
        ).fetchone()["c"]
    return {"created": created, "pending": total}


class MappingDecision(BaseModel):
    decision: str


@router.post("/api/mappings/{mapping_id}/decide")
def decide_mapping(
    mapping_id: str,
    body: MappingDecision,
    actor: str = Depends(auth.current_user),
) -> dict[str, Any]:
    try:
        with db.get_db() as conn:
            return alignment.decide(conn, mapping_id, body.decision, actor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "mapping not found") from exc


# ---------------- 账号 ----------------

class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/api/login")
def login(body: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    ip = request.client.host if request.client else "unknown"
    auth.check_login_rate(ip)
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM app_user WHERE username = ?", (body.username,)
        ).fetchone()
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    auth.reset_login_rate(ip)
    response.set_cookie(
        auth.COOKIE, auth.issue_token(body.username),
        httponly=True, samesite="lax", secure=auth.COOKIE_SECURE,
        max_age=auth.TTL_SECONDS,
    )
    return {"username": body.username, "role": row["role"]}


@router.post("/api/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    if not auth.AUTH_ENABLED:
        actor = request.headers.get("X-Actor") or "local"
        return {"auth": False, "actor": actor, "username": actor, "role": "admin"}
    username = auth.verify_token(request.cookies.get(auth.COOKIE))
    if not username:
        raise HTTPException(401, "login required")
    return {"auth": True, "username": username, "role": auth.role_of(username)}


@router.get("/api/users")
def list_users(
    actor: str = Depends(auth.require_role("admin")),
) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT username, role, created_at FROM app_user ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "member"


class PasswordIn(BaseModel):
    new_password: str
    old_password: str | None = None


@router.post("/api/users/{username}/password")
def change_password(
    username: str,
    body: PasswordIn,
    actor: str = Depends(auth.current_user),
) -> dict[str, Any]:
    if len(body.new_password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    role = auth.role_of(actor)
    if actor != username and role != "admin":
        raise HTTPException(403, "只能修改自己的密码")

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM app_user WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "用户不存在")
        if actor == username and auth.AUTH_ENABLED:
            if not body.old_password or not auth.verify_password(
                body.old_password, row["password_hash"]
            ):
                raise HTTPException(403, "原密码错误")
        conn.execute(
            "UPDATE app_user SET password_hash = ? WHERE username = ?",
            (auth.hash_password(body.new_password), username),
        )
    return {"ok": True, "username": username}


class RoleIn(BaseModel):
    role: str


@router.patch("/api/users/{username}")
def set_role(
    username: str, body: RoleIn, actor: str = Depends(auth.current_user)
) -> dict[str, Any]:
    if auth.role_of(actor) != "admin":
        raise HTTPException(403, "仅管理员可调整角色")
    if body.role not in ("admin", "manager", "member"):
        raise HTTPException(400, "role 只能是 admin/manager/member")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT username FROM app_user WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "用户不存在")
        conn.execute(
            "UPDATE app_user SET role = ? WHERE username = ?", (body.role, username)
        )
    return {"username": username, "role": body.role}


@router.post("/api/users")
def create_user(
    body: UserIn,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    if body.role not in ("admin", "manager", "member"):
        raise HTTPException(400, "role 只能是 admin/manager/member")
    with db.get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM app_user WHERE username = ?", (body.username,)
        ).fetchone()
        if exists:
            raise HTTPException(409, "user exists")
        conn.execute(
            "INSERT INTO app_user (username, password_hash, role, created_at)"
            " VALUES (?,?,?,?)",
            (body.username, auth.hash_password(body.password), body.role, db.now_iso()),
        )
    return {"username": body.username, "role": body.role}


# ---------------- 实验（holdout） ----------------

@router.get("/api/experiments/holdout")
def holdout_report(
    days: int = 30,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    window = f"-{days} days"
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT s.status, COALESCE(o.result, 'pending') AS result, COUNT(*) n"
            " FROM suggestion s LEFT JOIN outcome o ON o.suggestion_id = s.id"
            " WHERE s.status IN ('executed', 'holdout')"
            " AND datetime(s.created_at) >= datetime('now', ?)"
            " GROUP BY s.status, result",
            (window,),
        ).fetchall()
        holdout_targets = conn.execute(
            "SELECT id, title FROM target WHERE holdout = 1"
        ).fetchall()

    buckets: dict[str, dict[str, int]] = {"treatment": {}, "control": {}}
    for r in rows:
        group = "treatment" if r["status"] == "executed" else "control"
        buckets[group][r["result"]] = r["n"]

    def rate(d: dict[str, int]) -> float | None:
        decided = d.get("improved", 0) + d.get("unchanged", 0) + d.get("worse", 0)
        return round(d.get("improved", 0) / decided, 3) if decided else None

    return {
        "window_days": days,
        "treatment": {"results": buckets["treatment"], "improvement_rate": rate(buckets["treatment"])},
        "control": {"results": buckets["control"], "improvement_rate": rate(buckets["control"])},
        "holdout_targets": [dict(r) for r in holdout_targets],
        "note": "treatment=已执行，control=holdout 只观察；样本小时结论不可信",
    }


# ---------------- 指标 ----------------

@router.get("/api/metrics")
def model_metrics(
    hours: int = 24,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        return metrics.summary(conn, hours)


# ---------------- 运维 ----------------

@router.get("/api/ops")
def ops_state(
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        files = [
            dict(r) for r in conn.execute(
                "SELECT * FROM inbox_file ORDER BY processed_at DESC LIMIT 10"
            ).fetchall()
        ]
        m = metrics.summary(conn, 24)
        collection = collectors.health(conn)
        freshness = collectors.freshness(conn)
    pattern = "lira-*.sql" if db.BACKEND == "postgres" else "lira-*.db"
    backups = sorted(
        (p.name for p in (config.DATA_DIR / "backups").glob(pattern)), reverse=True
    )[:5] if (config.DATA_DIR / "backups").exists() else []
    return {
        "scheduler": scheduler.state(),
        "inbox": {
            "pending": inbox.pending_count(),
            "failed": inbox.failed_count(),
            "failed_files": inbox.failed_files(),
            "recent": files,
        },
        "collection": collection,
        "freshness": freshness,
        "auth_enabled": auth.AUTH_ENABLED,
        "webhook": notify.enabled(),
        "connector": {"configured": connectors.configured()},
        "metrics": m,
        "backups": backups,
    }


@router.get("/api/freshness")
def get_freshness() -> dict[str, Any]:
    with db.get_db() as conn:
        return collectors.freshness(conn)


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


@router.post("/api/ops/run")
def ops_run(
    kind: str,
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    try:
        detail = scheduler.run_now(kind)
    except KeyError as exc:
        raise HTTPException(400, f"unknown job: {kind}") from exc
    return {"kind": kind, "result": detail}


@router.post("/api/ops/inbox-scan")
def ops_inbox_scan(
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    return {"results": inbox.scan_once()}


# ---------------- 健康 ----------------

@router.get("/api/health")
def health() -> dict[str, Any]:
    with db.get_db() as conn:
        counts = {
            "targets": conn.execute("SELECT COUNT(*) c FROM target").fetchone()["c"],
            "snapshots": conn.execute("SELECT COUNT(*) c FROM snapshot").fetchone()["c"],
            "events": conn.execute("SELECT COUNT(*) c FROM event").fetchone()["c"],
            "suggestions": conn.execute("SELECT COUNT(*) c FROM suggestion").fetchone()["c"],
        }
        counts["cases"] = conn.execute('SELECT COUNT(*) c FROM "case"').fetchone()["c"]
        counts["mappings"] = conn.execute(
            "SELECT COUNT(*) c FROM mapping WHERE status = 'confirmed'"
        ).fetchone()["c"]
        counts["my_products"] = conn.execute(
            "SELECT COUNT(*) c FROM my_product"
        ).fetchone()["c"]
        counts["reviews"] = conn.execute(
            "SELECT COUNT(*) c FROM review"
        ).fetchone()["c"]
        counts["insights"] = conn.execute(
            "SELECT COUNT(*) c FROM review_insight"
        ).fetchone()["c"]
        last = conn.execute(
            "SELECT * FROM ingest_log ORDER BY received_at DESC LIMIT 1"
        ).fetchone()
        by_collector = conn.execute(
            "SELECT collector, COUNT(*) c, MAX(ts) last_ts FROM snapshot"
            " GROUP BY collector ORDER BY last_ts DESC"
        ).fetchall()
        freshness = collectors.freshness(conn)
    return {
        "ok": True,
        "counts": counts,
        "last_ingest": dict(last) if last else None,
        "collectors": [dict(r) for r in by_collector],
        "freshness": freshness,
        "llm_available": agent._llm_available(),
    }
