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

# ---------------- 运维 ----------------

@router.get("/api/ops")
def ops_state(
    actor: str = Depends(auth.require_role("admin")),
) -> dict[str, Any]:
    with db.get_db() as conn:
        m = metrics.summary(conn, 24)
        collection = collectors.health(conn)
        freshness = collectors.freshness(conn)
    pattern = "lira-*.sql"
    backups = sorted(
        (p.name for p in (config.DATA_DIR / "backups").glob(pattern)), reverse=True
    )[:5] if (config.DATA_DIR / "backups").exists() else []
    return {
        "scheduler": scheduler.state(),
        "collection": collection,
        "freshness": freshness,
        "auth_enabled": auth.AUTH_ENABLED,
        "metrics": m,
        "backups": backups,
    }

@router.get("/api/freshness")
def get_freshness() -> dict[str, Any]:
    with db.get_db() as conn:
        return collectors.freshness(conn)

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
        last = conn.execute(
            "SELECT * FROM ingest_log ORDER BY received_at DESC LIMIT 1"
        ).fetchone()
        by_collector = conn.execute(
            "SELECT collector, COUNT(*) c, MAX(ts) last_ts FROM snapshot"
            " GROUP BY collector ORDER BY last_ts DESC"
        ).fetchall()
        freshness = collectors.freshness(conn)

    store = vectorstore.PgVectorStore()
    indexed = sum(
        store.count(name) for name in store.collections("case_embeddings_")
    )
    vector_index = {
        "indexed": indexed,
        "cases": counts["cases"],
        "stale": indexed < counts["cases"],
    }
    return {
        "ok": True,
        "counts": counts,
        "last_ingest": dict(last) if last else None,
        "collectors": [dict(r) for r in by_collector],
        "freshness": freshness,
        "vector_index": vector_index,
        "llm_available": agent._llm_available(),
    }


@router.get("/api/tools")
def list_tools() -> list[dict[str, Any]]:
    """Agent 可调用的工具清单与风险等级（MCP 暴露同一契约）。"""
    from .. import tools as tool_registry

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "risk": tool.risk,
        }
        for tool in tool_registry.TOOLS.values()
    ]
