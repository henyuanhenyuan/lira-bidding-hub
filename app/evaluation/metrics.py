"""评测指标：全部为纯函数，便于单测与门禁复用。

回答类指标（faithfulness / relevance）需要判官；未启用判官时，
用确定性代理：证据闭包率、引用有效性、数值断言通过率。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def action_accuracy(results: Sequence[dict[str, Any]]) -> float:
    """期望动作与实际动作一致的比例。"""
    hits = sum(
        1 for item in results
        if item.get("actual_action") == item.get("expected_action")
    )
    return _ratio(hits, len(results))


def evidence_closure_rate(results: Sequence[dict[str, Any]]) -> float:
    """建议带证据的比例（无证据即整条作废，是业务硬约束）。"""
    hits = sum(1 for item in results if (item.get("evidence_count") or 0) > 0)
    return _ratio(hits, len(results))


def trace_completion_rate(results: Sequence[dict[str, Any]]) -> float:
    """Agent 轨迹包含必需阶段的比例。"""
    hits = sum(1 for item in results if item.get("trace_ok"))
    return _ratio(hits, len(results))


def citation_validity(cited: Iterable[str], allowed: Iterable[str]) -> float:
    """引用必须落在允许集合内；没有引用记为 0。"""
    cited_list = list(cited)
    if not cited_list:
        return 0.0
    allowed_set = set(allowed)
    return _ratio(sum(1 for item in cited_list if item in allowed_set), len(cited_list))


def recall_at_k(expected: Sequence[str], retrieved: Sequence[str], k: int = 5) -> float:
    if not expected:
        return 0.0
    top = set(retrieved[:k])
    return _ratio(sum(1 for item in expected if item in top), len(expected))


def reciprocal_rank(expected: Sequence[str], retrieved: Sequence[str]) -> float:
    wanted = set(expected)
    if not wanted:
        return 0.0
    for index, item in enumerate(retrieved, start=1):
        if item in wanted:
            return round(1 / index, 4)
    return 0.0


def mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    """判官与人工标注的一致度；样本不足或退化时返回 0。"""
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0
    total = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / total
    categories = set(labels_a) | set(labels_b)
    expected = 0.0
    for label in categories:
        pa = labels_a.count(label) / total
        pb = labels_b.count(label) / total
        expected += pa * pb
    if expected >= 1.0:
        return 0.0
    return round((observed - expected) / (1 - expected), 4)


def _slice(results: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        buckets.setdefault(str(item.get(key) or "unknown"), []).append(item)
    return {
        name: {
            "total": len(items),
            "passed": sum(1 for item in items if item.get("passed")),
            "action_accuracy": action_accuracy(items),
            "evidence_closure_rate": evidence_closure_rate(items),
        }
        for name, items in sorted(buckets.items())
    }


def aggregate(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """汇总总指标并按 segment / difficulty 切片。"""
    latencies = [
        item["latency_ms"] for item in results
        if isinstance(item.get("latency_ms"), (int, float))
    ]
    return {
        "total": len(results),
        "passed": sum(1 for item in results if item.get("passed")),
        "action_accuracy": action_accuracy(results),
        "evidence_closure_rate": evidence_closure_rate(results),
        "trace_completion_rate": trace_completion_rate(results),
        "avg_latency_ms": round(mean(latencies), 1),
        "by_segment": _slice(results, "segment"),
        "by_difficulty": _slice(results, "difficulty"),
    }


def compare(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    delta_tolerance: float = 0.02,
    floors: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """floor + delta 双门限比较，返回违规列表（空表示通过）。"""
    floors = floors or {
        "action_accuracy": 0.9,
        "evidence_closure_rate": 1.0,
        "trace_completion_rate": 1.0,
    }
    violations: list[dict[str, Any]] = []
    for name, floor in floors.items():
        value = float(current.get(name) or 0.0)
        if value < floor:
            violations.append(
                {"metric": name, "kind": "floor", "value": value, "threshold": floor}
            )
        base = baseline.get(name)
        if isinstance(base, (int, float)) and value < base - delta_tolerance:
            violations.append(
                {
                    "metric": name, "kind": "delta", "value": value,
                    "baseline": base, "tolerance": delta_tolerance,
                }
            )
    return violations
