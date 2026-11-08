"""评测运行器：选 tier → 落库 → 跑金标 → 汇总指标 → 归档坏例与产物。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config, db
from .. import eval as eval_store
from . import datasets, metrics

RESULT_DIR = Path(config.DATA_DIR) / "eval" / "results"


def _enrich(results: list[dict[str, Any]], meta: dict[str, datasets.GoldenCase]) -> None:
    for item in results:
        case = meta.get(item.get("case") or "")
        item["segment"] = case.segment if case else "unknown"
        item["difficulty"] = case.difficulty if case else "unknown"
        item["expected_chunks"] = list(case.expected_chunks) if case else []


def _reason(item: dict[str, Any]) -> str:
    if item.get("error"):
        return f"执行错误：{item['error']}"
    if item.get("actual_action") != item.get("expected_action"):
        return (
            f"动作不符：期望 {item.get('expected_action')}，"
            f"实际 {item.get('actual_action')}"
        )
    if not (item.get("evidence_count") or 0):
        return "缺少证据"
    if not item.get("trace_ok"):
        return "轨迹不完整"
    return "未通过"


def _archive(conn, run_key: str, results: list[dict[str, Any]]) -> int:
    archived = 0
    for item in results:
        if item.get("passed"):
            continue
        conn.execute(
            "INSERT INTO eval_badcase (id, run_key, case_name, segment, difficulty,"
            " reason, detail, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                db.new_id(), run_key, item.get("case") or "", item.get("segment"),
                item.get("difficulty"), _reason(item),
                json.dumps(item, ensure_ascii=False), db.now_iso(),
            ),
        )
        archived += 1
    return archived


def run(
    tier: str = "smoke",
    limit: int | None = None,
    use_judge: bool = False,
    use_llm: bool = False,
    write_artifact: bool = True,
) -> dict[str, Any]:
    cases = datasets.select(datasets.load(), tier)
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError(f"tier={tier} 没有可用用例")

    with db.get_db() as conn:
        datasets.seed(conn, cases)

    meta = datasets.by_name(cases)
    # 评测默认走确定性模板：动作由策略决定，模型只影响措辞，
    # 关掉模型既保证可复现，也避免每次评测都打本地模型。
    previous_llm = config.LLM_ENABLED
    if not use_llm:
        config.LLM_ENABLED = "off"
    try:
        raw = eval_store.run(names=set(meta))
    finally:
        config.LLM_ENABLED = previous_llm
    results = raw["results"]
    _enrich(results, meta)
    summary = metrics.aggregate(results)
    summary["tier"] = tier

    with db.get_db() as conn:
        conn.execute(
            "UPDATE eval_run SET tier = ?, metrics = ? WHERE run_key = ?",
            (tier, json.dumps(summary, ensure_ascii=False), raw["run_key"]),
        )
        summary["badcases"] = _archive(conn, raw["run_key"], results)

    if write_artifact:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        artifact = RESULT_DIR / f"{raw['run_key']}.json"
        artifact.write_text(
            json.dumps(
                {"run_key": raw["run_key"], "tier": tier,
                 "metrics": summary, "results": results},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        summary["artifact"] = str(artifact)

    return {
        "run_key": raw["run_key"],
        "tier": tier,
        "total": raw["total"],
        "passed": raw["passed"],
        "accuracy": raw["accuracy"],
        "metrics": summary,
        "results": results,
    }


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT run_key, total, passed, accuracy, tier, metrics, created_at"
            " FROM eval_run ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **dict(row),
            "metrics": json.loads(row["metrics"]) if row["metrics"] else None,
        }
        for row in rows
    ]


def list_badcases(run_key: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = (
        "SELECT case_name, segment, difficulty, reason, created_at"
        " FROM eval_badcase"
    )
    params: list[Any] = []
    if run_key:
        sql += " WHERE run_key = ?"
        params.append(run_key)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with db.get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
