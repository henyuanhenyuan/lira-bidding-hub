"""轻量 span 追踪：trace_id + 父子关系，默认落库，可选导出 OTLP。

不引入 OpenTelemetry SDK；需要时可用 LIRA_OTEL_ENDPOINT 接自建 Collector。
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from . import db

_trace_id: ContextVar[str] = ContextVar("lira_trace_id", default="")
_span_id: ContextVar[str] = ContextVar("lira_span_id", default="")
_buffer: list[dict[str, Any]] = []


def new_trace() -> str:
    trace_id = db.new_id()
    _trace_id.set(trace_id)
    _span_id.set("")
    return trace_id


def current_trace() -> str:
    return _trace_id.get()


def set_trace(trace_id: str) -> None:
    _trace_id.set(trace_id)


def set_span(span_id: str):
    """把后续 span 挂到指定父节点上；返回用于恢复的 token。"""
    return _span_id.set(span_id)


def reset_span(token) -> None:
    _span_id.reset(token)


def record(
    name: str,
    kind: str = "span",
    *,
    status: str = "ok",
    attributes: dict[str, Any] | None = None,
    duration_ms: int = 0,
    run_id: str | None = None,
    parent_id: str | None = None,
) -> str:
    trace_id = _trace_id.get() or new_trace()
    span_id = db.new_id()
    row = {
        "id": span_id, "trace_id": trace_id,
        "parent_id": parent_id if parent_id is not None else (_span_id.get() or None),
        "run_id": run_id, "name": name[:120], "kind": kind, "status": status,
        "attributes": json.dumps(attributes or {}, ensure_ascii=False)[:4000],
        "started_at": db.now_iso(), "duration_ms": int(duration_ms),
        "created_at": db.now_iso(),
    }
    _buffer.append(row)
    del _buffer[:-32]
    _flush_row(row)
    return span_id


def _flush_row(row: dict[str, Any]) -> None:
    try:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO span (id, trace_id, parent_id, run_id, name, kind,"
                " status, attributes, started_at, duration_ms, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"], row["trace_id"], row["parent_id"], row["run_id"],
                    row["name"], row["kind"], row["status"], row["attributes"],
                    row["started_at"], row["duration_ms"], row["created_at"],
                ),
            )
    except Exception:  # 追踪失败绝不影响主流程
        return


@contextmanager
def span(name: str, kind: str = "span", **attributes: Any) -> Iterator[str]:
    started = time.perf_counter()
    parent = _span_id.get()
    span_id = record(name, kind, attributes=attributes)
    token = _span_id.set(span_id)
    try:
        yield span_id
    except Exception as exc:
        record(name + ".error", kind, status="error",
               attributes={"error": str(exc)[:200]}, parent_id=span_id)
        raise
    finally:
        _span_id.reset(token)
        duration = int((time.perf_counter() - started) * 1000)
        _update_duration(span_id, duration)


def _update_duration(span_id: str, duration_ms: int) -> None:
    try:
        with db.get_db() as conn:
            conn.execute(
                "UPDATE span SET duration_ms = ? WHERE id = ?", (duration_ms, span_id)
            )
    except Exception:
        return


def list_trace(trace_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM span WHERE trace_id = ? ORDER BY created_at, id",
            (trace_id,),
        ).fetchall()
    nodes = []
    for row in rows:
        item = dict(row)
        item["attributes"] = json.loads(item.get("attributes") or "{}")
        nodes.append(item)
    roots = [node for node in nodes if not node.get("parent_id")]
    children: dict[str, list[dict]] = {}
    for node in nodes:
        if node.get("parent_id"):
            children.setdefault(node["parent_id"], []).append(node)
    for node in nodes:
        node["children"] = children.get(node["id"], [])
    return {"trace_id": trace_id, "count": len(nodes), "roots": roots}
