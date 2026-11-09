from __future__ import annotations

import os
import time
from typing import Any

from . import collect_logs, collect_tasks, db, ingest, ratelimit, review_queue, risk
from .channels import get_adapter

DEFAULT_ACCOUNT = os.getenv("LIRA_COLLECT_ACCOUNT", "default")
DEFAULT_SHOP = os.getenv("LIRA_COLLECT_SHOP", "default")
RL_RATE = float(os.getenv("LIRA_RL_RATE", "0.2"))
RL_CAPACITY = int(os.getenv("LIRA_RL_CAPACITY", "1"))
SKIP_RETRY_S = float(os.getenv("LIRA_COLLECT_SKIP_RETRY", "3600"))
CIRCUIT_RETRY_S = float(os.getenv("LIRA_COLLECT_CIRCUIT_RETRY", "300"))
RISK_THRESHOLD = int(os.getenv("LIRA_RISK_THRESHOLD", "3"))
RISK_COOLDOWN_S = float(os.getenv("LIRA_RISK_COOLDOWN", "600"))
STALE_AFTER_S = float(os.getenv("LIRA_COLLECT_STALE", "900"))


def _error_kind(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    body = ""
    if response is not None:
        try:
            body = response.text or ""
        except Exception:
            body = ""
    return risk.classify(status_code=status, body=body or str(exc)) or "exception"


def recover_stale(*, older_than_s: float | None = None) -> int:
    """worker 崩溃后把卡在 running 的任务放回 pending。"""
    with db.get_db() as conn:
        return collect_tasks.release_stale(
            conn,
            older_than_s=STALE_AFTER_S if older_than_s is None else older_than_s,
        )


def dispatch_due(
    channel: str,
    *,
    limit: int = 5,
    adapter: Any | None = None,
    rate: float | None = None,
    capacity: int | None = None,
    rl_client: Any | None = None,
    risk_client: Any | None = None,
    now: float | None = None,
) -> dict[str, int]:
    """领取到期任务，经限流与熔断后下发。任务生命周期止于下发完成，结果回收由 ingest 负责。"""
    adapter = adapter or get_adapter(channel)
    rate = RL_RATE if rate is None else rate
    capacity = RL_CAPACITY if capacity is None else capacity
    at = time.time() if now is None else now

    with db.get_db() as conn:
        tasks = collect_tasks.claim(conn, channel=channel, limit=limit)

    summary = {"claimed": len(tasks), "done": 0, "pending": 0, "skipped": 0,
               "blocked": 0, "error": 0}

    for task in tasks:
        task_id = task["id"]
        account = task.get("account") or DEFAULT_ACCOUNT
        shop = task.get("shop") or DEFAULT_SHOP
        with db.get_db() as conn:
            target = conn.execute(
                "SELECT url, price_selector FROM target WHERE id = ?",
                (task["target_id"],),
            ).fetchone()
        if target:
            task = {**task, "url": target["url"], "price_selector": target["price_selector"]}

        if not risk.allow(channel, account, shop, client=risk_client, now=at):
            with db.get_db() as conn:
                collect_tasks.defer(conn, task_id, delay_s=CIRCUIT_RETRY_S)
                review_queue.enqueue(
                    conn, task_id=task_id, channel=channel,
                    target_id=task["target_id"], reason="circuit open",
                )
                collect_logs.record(
                    conn, task_id=task_id, channel=channel, account=account,
                    shop=shop, outcome="error", error_kind="circuit_open",
                )
            summary["blocked"] += 1
            continue

        if not ratelimit.acquire(
            channel, account, shop, rate=rate, capacity=capacity,
            client=rl_client, now=at,
        ):
            wait = ratelimit.wait_seconds(
                channel, account, shop, rate=rate, client=rl_client, now=at
            )
            with db.get_db() as conn:
                collect_tasks.defer(conn, task_id, delay_s=max(wait, 1.0))
                collect_logs.record(
                    conn, task_id=task_id, channel=channel, account=account,
                    shop=shop, outcome="error", error_kind="rate_limited",
                )
            summary["blocked"] += 1
            continue

        began = time.perf_counter()
        try:
            result = adapter.dispatch(task)
        except Exception as exc:
            kind = _error_kind(exc)
            opened = risk.record_failure(
                channel, account, shop, kind=kind,
                threshold=RISK_THRESHOLD, cooldown_s=RISK_COOLDOWN_S,
                client=risk_client,
            )
            with db.get_db() as conn:
                collect_tasks.fail(conn, task_id, str(exc))
                if opened == "open":
                    review_queue.enqueue(
                        conn, task_id=task_id, channel=channel,
                        target_id=task["target_id"], reason=f"circuit open: {kind}",
                    )
                collect_logs.record(
                    conn, task_id=task_id, channel=channel, account=account,
                    shop=shop, outcome="error", error_kind=kind,
                    detail=str(exc),
                )
            summary["error"] += 1
            continue

        latency_ms = int((time.perf_counter() - began) * 1000)
        with db.get_db() as conn:
            interval = int(task.get("interval_s") or 0)
            if result.status == "skipped":
                collect_tasks.fail(
                    conn, task_id, result.detail or "skipped",
                    retry_delay_s=SKIP_RETRY_S,
                )
            else:
                if result.status == "done":
                    if result.observations:
                        ingest.ingest(conn, result.observations, source=channel)
                risk.record_success(channel, account, shop, client=risk_client)
                if interval > 0:
                    collect_tasks.reschedule(conn, task_id, interval_s=interval)
                else:
                    collect_tasks.complete(conn, task_id)
            collect_logs.record(
                conn, task_id=task_id, channel=channel, account=account,
                shop=shop, latency_ms=latency_ms, outcome=result.status,
                detail=result.detail,
            )
        summary[result.status] = summary.get(result.status, 0) + 1

    return summary
