from __future__ import annotations

import os

from . import metrics

MIN_ACCURACY = float(os.getenv("LIRA_GATE_MIN_ACCURACY", "0.8"))
MAX_FALLBACK_RATE = float(os.getenv("LIRA_GATE_MAX_FALLBACK_RATE", "0.6"))
ENFORCE = os.getenv("LIRA_GATE_ENFORCE", "off") == "on"


def status(conn) -> dict:
    latest = conn.execute(
        "SELECT * FROM eval_run ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    usage = metrics.summary(conn, 24)
    reasons: list[str] = []
    warnings: list[str] = []
    latest_eval = None
    eval_ok = False

    if latest:
        accuracy = float(latest["accuracy"])
        latest_eval = {
            "run_key": latest["run_key"],
            "total": latest["total"],
            "passed": latest["passed"],
            "accuracy": accuracy,
            "created_at": latest["created_at"],
        }
        eval_ok = accuracy >= MIN_ACCURACY
        if not eval_ok:
            reasons.append(
                f"最近一次评测通过率 {accuracy:.0%}，低于阈值 {MIN_ACCURACY:.0%}"
            )
    else:
        reasons.append("还没有评测记录")

    if usage["calls"] and usage["fallback_rate"] > MAX_FALLBACK_RATE:
        warnings.append(
            f"模型回退率 {usage['fallback_rate']:.0%}，高于 {MAX_FALLBACK_RATE:.0%}"
        )
    if usage["budget_used_ratio"] is not None and usage["budget_used_ratio"] >= 1:
        warnings.append("24 小时 token 预算已用尽，模型调用会回退模板")

    return {
        "ok": eval_ok,
        "enforced": ENFORCE,
        "thresholds": {
            "min_accuracy": MIN_ACCURACY,
            "max_fallback_rate": MAX_FALLBACK_RATE,
        },
        "reasons": reasons,
        "warnings": warnings,
        "latest_eval": latest_eval,
        "usage": {
            "calls": usage["calls"],
            "tokens": usage["tokens"],
            "cost": usage["cost"],
            "fallback_rate": usage["fallback_rate"],
            "budget_used_ratio": usage["budget_used_ratio"],
        },
    }
