from __future__ import annotations

import json
import os
from typing import Any

import httpx

from . import approval, db, guardrail

MODE = os.getenv("LIRA_EXECUTOR_MODE", "off")  # off | preview | webhook
URL = os.getenv("LIRA_EXECUTOR_URL", "")
ROLLBACK_URL = os.getenv("LIRA_EXECUTOR_ROLLBACK_URL", "")
TOKEN = os.getenv("LIRA_EXECUTOR_TOKEN", "")


class ExecutorError(RuntimeError):
    pass


def _load(conn, suggestion_id: str):
    return conn.execute(
        "SELECT s.*, e.target_id, e.ts AS event_ts, t.my_sku, t.my_price,"
        " t.title AS target_title, p.cost, p.margin_floor AS product_floor"
        " FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " LEFT JOIN my_product p ON p.sku = t.my_sku"
        " WHERE s.id = ?",
        (suggestion_id,),
    ).fetchone()


def _lookup(conn, base_key: str):
    return conn.execute(
        "SELECT * FROM execution WHERE idempotency_key = ?"
        " OR idempotency_key LIKE ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (base_key, f"{base_key}:%"),
    ).fetchone()


def _plan(row, executed_price: float | None) -> dict[str, Any]:
    to_price = executed_price if executed_price is not None else row["target_price"]
    if to_price is None:
        raise ExecutorError("这条建议没有可执行的目标价")
    floor = row["product_floor"] if row["product_floor"] is not None else 0.15
    check = guardrail.evaluate(float(to_price), row["cost"], floor)
    key = f"{row['id']}:{float(to_price):.2f}:{MODE}"
    return {
        "suggestion_id": row["id"],
        "action": row["action"],
        "target_id": row["target_id"],
        "target_title": row["target_title"],
        "sku": row["my_sku"],
        "from_price": row["my_price"],
        "to_price": round(float(to_price), 2),
        "margin_at_target": check.margin,
        "margin_floor": check.floor,
        "guardrail": check.status,
        "guardrail_note": check.note,
        "mode": MODE,
        "idempotency_key": key,
    }


def preview(suggestion_id: str) -> dict[str, Any]:
    with db.get_db() as conn:
        row = _load(conn, suggestion_id)
        if not row:
            raise KeyError(suggestion_id)
        plan = _plan(row, None)
        existing = _lookup(conn, plan["idempotency_key"])
    return {
        "plan": plan,
        "configured": MODE != "webhook" or bool(URL),
        "execution": _row(existing) if existing else None,
    }


def _row(row) -> dict[str, Any]:
    result = dict(row)
    for key in ("request", "response"):
        if result.get(key):
            parsed = db.loads(result[key], None)
            result[key] = parsed if parsed is not None else result[key]
    return result


def run(
    suggestion_id: str,
    actor: str,
    role: str,
    executed_price: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    with db.get_db() as conn:
        row = _load(conn, suggestion_id)
        if not row:
            raise KeyError(suggestion_id)
        plan = _plan(row, executed_price)
        base_key = plan["idempotency_key"]
        existing = _lookup(conn, base_key)
        if existing and existing["status"] in ("succeeded", "recorded", "preview"):
            return {**_row(existing), "plan": plan, "idempotent": True}
        if row["status"] != "approved":
            raise ExecutorError(f"当前状态 {row['status']} 不可执行")
        if plan["guardrail"] == "blocked" and role not in ("admin", "manager"):
            raise ExecutorError("执行价触碰毛利护栏，需要管理员操作")
        if existing is not None:
            # 回滚或失败后重试：新开一次尝试，避免撞唯一键
            plan["idempotency_key"] = f"{base_key}:{db.new_id()[:8]}"

    execution_id = db.new_id()
    request = {**plan, "actor": actor, "note": note}
    try:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO execution (id, suggestion_id, mode, status, request,"
                " idempotency_key, actor, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    execution_id, suggestion_id, MODE, "pending",
                    json.dumps(request, ensure_ascii=False),
                    plan["idempotency_key"], actor, db.now_iso(),
                ),
            )
    except Exception as exc:
        if not db.is_unique_violation(exc):
            raise
        with db.get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM execution WHERE idempotency_key = ?",
                (plan["idempotency_key"],),
            ).fetchone()
        return {**_row(existing), "plan": plan, "idempotent": True}

    if MODE == "webhook":
        if not URL:
            _finish(execution_id, "failed", None, None, "LIRA_EXECUTOR_URL 未配置")
            raise ExecutorError("外部执行未配置：请设置 LIRA_EXECUTOR_URL")
        headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
        try:
            response = httpx.post(URL, json=request, headers=headers, timeout=10.0)
            response.raise_for_status()
            body = response.json() if response.content else {}
        except Exception as exc:
            _finish(execution_id, "failed", None, None, str(exc))
            raise ExecutorError(f"外部执行失败：{exc}") from exc
        external_id = str(
            body.get("external_id") or body.get("id") or body.get("task_id") or ""
        ) or None
        _finish(execution_id, "succeeded", external_id, body, None)
    elif MODE == "preview":
        _finish(execution_id, "preview", None, {"preview": True}, None)
    else:
        _finish(execution_id, "recorded", None, {"recorded": True}, None)

    with db.get_db() as conn:
        saved = conn.execute(
            "SELECT * FROM execution WHERE id = ?", (execution_id,)
        ).fetchone()
    return {**_row(saved), "plan": plan, "idempotent": False}


def _finish(
    execution_id: str,
    status: str,
    external_id: str | None,
    response: Any,
    error: str | None,
) -> None:
    with db.get_db() as conn:
        conn.execute(
            "UPDATE execution SET status = ?, external_id = ?, response = ?,"
            " error = ? WHERE id = ?",
            (
                status, external_id,
                json.dumps(response, ensure_ascii=False) if response is not None else None,
                error, execution_id,
            ),
        )


def history(conn, suggestion_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM execution WHERE suggestion_id = ? ORDER BY created_at DESC",
        (suggestion_id,),
    ).fetchall()
    return [_row(row) for row in rows]


def get(execution_id: str) -> dict[str, Any] | None:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM execution WHERE id = ?", (execution_id,)
        ).fetchone()
    return _row(row) if row else None


def rollback(execution_id: str, actor: str, role: str) -> dict[str, Any]:
    with db.get_db() as conn:
        execution = conn.execute(
            "SELECT * FROM execution WHERE id = ?", (execution_id,)
        ).fetchone()
        if not execution:
            raise KeyError(execution_id)
        if execution["status"] not in ("succeeded", "recorded", "preview"):
            raise ExecutorError(f"执行状态 {execution['status']} 不可回滚")
        suggestion_id = execution["suggestion_id"]

    if MODE == "webhook":
        if not ROLLBACK_URL:
            raise ExecutorError("回滚地址未配置：请设置 LIRA_EXECUTOR_ROLLBACK_URL")
        headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
        try:
            response = httpx.post(
                ROLLBACK_URL,
                json={
                    "execution_id": execution_id,
                    "external_id": execution["external_id"],
                    "suggestion_id": suggestion_id,
                },
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
        except Exception as exc:
            raise ExecutorError(f"外部回滚失败：{exc}") from exc

    with db.get_db() as conn:
        approval.rollback(conn, suggestion_id, actor, role, "回滚执行")
        conn.execute(
            "UPDATE execution SET status = 'rolled_back', rolled_back_at = ?"
            " WHERE id = ?",
            (db.now_iso(), execution_id),
        )
    return get(execution_id) or {}
