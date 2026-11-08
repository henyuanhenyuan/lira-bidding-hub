from __future__ import annotations

import contextvars
import os

from . import db

# 指标属于尽力而为：写不进去也不能影响主流程
TIMEOUT_S = 0.5
COST_PER_1K_TOKENS = float(os.getenv("LIRA_COST_PER_1K_TOKENS", "0"))
DAILY_TOKEN_BUDGET = int(os.getenv("LIRA_DAILY_TOKEN_BUDGET", "0"))

_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lira_agent_run_id", default=None
)


def set_run_id(run_id: str):
    return _run_id.set(run_id)


def reset_run_id(token) -> None:
    _run_id.reset(token)


def current_run_id() -> str | None:
    return _run_id.get()


def _cost(prompt_tokens: int, completion_tokens: int) -> float:
    tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    return round(tokens / 1000 * COST_PER_1K_TOKENS, 6)


def record(
    kind: str,
    *,
    model: str = "",
    ok: bool = True,
    latency_ms: int | None = None,
    fallback: bool = False,
    detail: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    run_id: str | None = None,
    provider: str = "",
    prompt_name: str = "",
    prompt_version: str = "",
    trace_id: str = "",
    cost: float | None = None,
) -> None:
    try:
        conn = db.connect()
        if db.BACKEND == "sqlite":
            conn.execute("PRAGMA busy_timeout = 500")
        from .safety.redact import redact

        detail = redact(detail or "")[0]
        try:
            conn.execute(
                "INSERT INTO model_call (id, kind, model, ok, fallback, latency_ms,"
                " detail, run_id, prompt_tokens, completion_tokens, cost, provider,"
                " prompt_name, prompt_version, trace_id, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    db.new_id(), kind, model, int(ok), int(fallback), latency_ms,
                    (detail or "")[:200],
                    run_id if run_id is not None else current_run_id(),
                    int(prompt_tokens or 0), int(completion_tokens or 0),
                    _cost(prompt_tokens, completion_tokens) if cost is None else cost,
                    provider, prompt_name, prompt_version, trace_id, db.now_iso(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        if db.is_db_error(exc):
            return
        raise


def summary(conn, hours: int = 24) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS calls, SUM(ok) AS ok, SUM(fallback) AS fallback,"
        " AVG(latency_ms) AS avg_ms, SUM(prompt_tokens) AS prompt_tokens,"
        " SUM(completion_tokens) AS completion_tokens, SUM(cost) AS cost"
        " FROM model_call WHERE datetime(created_at) >= datetime('now', ?)",
        (f"-{hours} hours",),
    ).fetchone()
    calls = row["calls"] or 0
    latencies = [
        r["latency_ms"] for r in conn.execute(
            "SELECT latency_ms FROM model_call WHERE latency_ms IS NOT NULL"
            " AND datetime(created_at) >= datetime('now', ?)"
            " ORDER BY latency_ms",
            (f"-{hours} hours",),
        ).fetchall()
    ]
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else None
    by_kind = [
        dict(r) for r in conn.execute(
            "SELECT kind, COUNT(*) n, SUM(fallback) fallback FROM model_call"
            " WHERE datetime(created_at) >= datetime('now', ?) GROUP BY kind",
            (f"-{hours} hours",),
        ).fetchall()
    ]
    prompt_tokens = int(row["prompt_tokens"] or 0)
    completion_tokens = int(row["completion_tokens"] or 0)
    tokens = prompt_tokens + completion_tokens
    return {
        "window_hours": hours,
        "calls": calls,
        "ok": row["ok"] or 0,
        "fallback": row["fallback"] or 0,
        "fallback_rate": round((row["fallback"] or 0) / calls, 3) if calls else 0.0,
        "avg_latency_ms": round(float(row["avg_ms"]), 1) if row["avg_ms"] else None,
        "p95_latency_ms": p95,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": tokens,
        "cost": round(float(row["cost"] or 0), 6),
        "daily_budget_tokens": DAILY_TOKEN_BUDGET,
        "budget_used_ratio": (
            round(tokens / DAILY_TOKEN_BUDGET, 3) if DAILY_TOKEN_BUDGET > 0 else None
        ),
        "by_kind": by_kind,
        "by_model": _by_model(conn),
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p99_latency_ms": _percentile(latencies, 0.99),
    }


def _percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * ratio))
    return ordered[index]


def _by_model(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT COALESCE(NULLIF(model, ''), 'unknown') AS model,"
        " COUNT(*) AS calls, SUM(COALESCE(fallback, 0)) AS fallback,"
        " SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)) AS tokens,"
        " SUM(COALESCE(cost, 0)) AS cost"
        " FROM model_call GROUP BY COALESCE(NULLIF(model, ''), 'unknown')"
        " ORDER BY calls DESC LIMIT 20"
    ).fetchall()
    return [
        {
            "model": row["model"], "calls": row["calls"],
            "fallback": row["fallback"] or 0,
            "tokens": int(row["tokens"] or 0),
            "cost": round(float(row["cost"] or 0), 6),
        }
        for row in rows
    ]


def budget_exceeded() -> bool:
    if DAILY_TOKEN_BUDGET <= 0:
        return False
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(prompt_tokens), 0) + COALESCE(SUM(completion_tokens), 0)"
                " AS tokens FROM model_call"
                " WHERE datetime(created_at) >= datetime('now', ?)",
                ("-24 hours",),
            ).fetchone()
        return int(row["tokens"] or 0) >= DAILY_TOKEN_BUDGET
    except Exception:
        return False
