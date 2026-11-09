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


# ---------------- 采集 ----------------

@router.post("/v1/ingest/snapshots")
def ingest_snapshots(batch: IngestBatch) -> dict[str, Any]:
    with db.get_db() as conn:
        report = ingest.ingest(conn, batch.snapshots, source="api", file_name=batch.file_name)
    return report.as_dict()


@router.post("/v1/ingest/validate")
def validate_batch(batch: IngestBatch) -> dict[str, Any]:
    """干跑：只校验契约，不落库。给采集端自查用。"""
    errors: list[dict[str, Any]] = []
    for index, snapshot in enumerate(batch.snapshots):
        if snapshot.observation.list_price is None:
            errors.append(
                {
                    "index": index,
                    "target_id": snapshot.target_id,
                    "error": "list_price is required",
                }
            )
    return {"ok": not errors, "rows": len(batch.snapshots), "errors": errors}


# ---------------- 目标 ----------------

@router.get("/api/targets")
def list_targets() -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, platform, title, my_sku, my_price, active, mapping_status, holdout"
            " FROM target ORDER BY title"
        ).fetchall()
    return [dict(r) for r in rows]


MAX_UPLOAD = 20 * 1024 * 1024


def _excel_rows(raw: bytes) -> list[dict[str, Any]]:
    """读 Excel 首个工作表，首行为表头。"""
    import io

    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = book.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    try:
        header = [str(cell or "").strip() for cell in next(rows)]
    except StopIteration:
        return []
    out: list[dict[str, Any]] = []
    for values in rows:
        out.append(
            {
                header[i]: ("" if value is None else str(value))
                for i, value in enumerate(values)
                if i < len(header) and header[i]
            }
        )
    return out


def _parse_file(raw: bytes, filename: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """支持 CSV / Excel / JSON；返回 (快照, 错误)。"""
    import csv
    import io
    import json as _json

    errors: list[dict[str, Any]] = []
    lower = filename.lower()
    if lower.endswith(".json"):
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            data = _json.loads(text)
        except ValueError as exc:
            return [], [{"line": 0, "error": f"JSON 解析失败：{exc}"}]
        rows = data.get("snapshots") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return [], [{"line": 0, "error": "JSON 需要是快照数组"}]
        return rows, errors

    if lower.endswith((".xlsx", ".xlsm")):
        try:
            records = _excel_rows(raw)
        except Exception as exc:
            return [], [{"line": 0, "error": f"Excel 解析失败：{exc}"}]
        rows_iter = enumerate(records, start=2)
    else:
        text = raw.decode("utf-8-sig", errors="replace")
        rows_iter = enumerate(csv.DictReader(io.StringIO(text)), start=2)

    snapshots: list[dict[str, Any]] = []
    for index, row in rows_iter:
        try:
            price = float(str(row.get("list_price") or "").strip())
        except ValueError:
            errors.append({"line": index, "error": "list_price 不是数字"})
            continue
        target = (row.get("target_id") or "").strip()
        if not target:
            errors.append({"line": index, "error": "target_id 为空"})
            continue
        observation: dict[str, Any] = {"list_price": price}
        if row.get("title"):
            observation["title"] = row["title"].strip()
        if row.get("region"):
            observation["region"] = row["region"].strip()
        observation["account_tier"] = (row.get("account_tier") or "normal").strip()
        snapshots.append(
            {
                "target_id": target,
                "ts": (row.get("ts") or "").strip() or db.now_iso(),
                "collector": (row.get("collector") or "file").strip(),
                "source_tier": int(row.get("source_tier") or 3),
                "observation": observation,
            }
        )
    return snapshots, errors


@router.post("/api/import/file")
async def import_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """文件接入：CSV（target_id,ts,list_price,title,source_tier）或 JSON 快照数组。"""
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (max 20MB)")
    rows, parse_errors = _parse_file(raw, file.filename or "upload.csv")
    if not rows:
        return {"ok": False, "rows": 0, "errors": parse_errors}

    snapshots = []
    for index, item in enumerate(rows):
        try:
            snapshots.append(SnapshotIn(**item))
        except Exception as exc:  # 契约校验失败
            parse_errors.append({"line": index + 2, "error": str(exc)[:120]})

    if not snapshots:
        return {"ok": False, "rows": 0, "errors": parse_errors}

    with db.get_db() as conn:
        report = ingest.ingest(conn, snapshots, source="file", file_name=file.filename)
    out = report.as_dict()
    out["errors"] = parse_errors + out.get("errors", [])
    out["rows_rejected"] = out.get("rows_rejected", 0) + len(parse_errors)
    return out
