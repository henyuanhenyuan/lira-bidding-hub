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
