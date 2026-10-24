from __future__ import annotations

from .contracts import EvidenceCheck


def validate(evidence_ids: list[str], allowed: set[str]) -> EvidenceCheck:
    """证据闭包：任何一条引用必须存在于本次上下文允许集合内。"""
    valid: list[str] = []
    invalid: list[str] = []
    for eid in evidence_ids:
        if eid in allowed:
            if eid not in valid:
                valid.append(eid)
        else:
            invalid.append(eid)
    return EvidenceCheck(ok=not invalid and bool(valid), valid=valid, invalid=invalid)


def confidence_ceiling(evidence_count: int, requested: float) -> float:
    """证据少时不允许给出过高的置信度。"""
    if evidence_count <= 0:
        return min(requested, 0.30)
    if evidence_count == 1:
        return min(requested, 0.60)
    if evidence_count == 2:
        return min(requested, 0.80)
    return min(requested, 0.95)
