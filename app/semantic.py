from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import embeddings, images

RULE_VERSION = "semantic-v2"
L2_SIMILARITY = 0.60

_SPLIT = re.compile(r"[·・|、,，/／;；:：()（）\[\]【】\s]+")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def similarity(a: str, b: str) -> float:
    """向量余弦。同一 embedding 提供方下比较，提供方不一致直接判为不同。"""
    if normalize(a) == normalize(b):
        return 1.0
    va, provider_a = embeddings.embed(a)
    vb, provider_b = embeddings.embed(b)
    if provider_a != provider_b or len(va) != len(vb):
        return 0.0
    score = sum(x * y for x, y in zip(va, vb))
    return max(0.0, min(1.0, score))


def claims(title: str) -> set[str]:
    return {p for p in _SPLIT.split(title or "") if len(p) >= 2}


@dataclass
class Change:
    field: str
    similarity: float
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    severity: str = "L1"
    note: str = ""


def detect(prev: dict | None, cur: dict) -> list[Change]:
    if not prev:
        return []

    changes: list[Change] = []

    pt, ct = (prev.get("title") or "").strip(), (cur.get("title") or "").strip()
    if pt and ct and normalize(pt) != normalize(ct):
        sim = round(similarity(pt, ct), 3)
        pc, cc = claims(pt), claims(ct)
        added = sorted(cc - pc)
        removed = sorted(pc - cc)
        sev = "L2" if sim < L2_SIMILARITY else "L1"

        bits = []
        if added:
            bits.append("新增 " + "、".join(added[:4]))
        if removed:
            bits.append("删除 " + "、".join(removed[:4]))
        detail = "；".join(bits) if bits else "整体重写"
        changes.append(
            Change(
                field="title",
                similarity=sim,
                added=added,
                removed=removed,
                severity=sev,
                note=f"标题变化（相似度 {sim:.0%}）：{detail}",
            )
        )

    prev_fp = images.fp_of(prev)
    cur_fp = images.fp_of(cur)
    if prev_fp and cur_fp and prev_fp != cur_fp:
        changes.append(
            Change(
                field="image",
                similarity=0.0,
                severity="L1",
                note="主图已更换",
            )
        )

    return changes


def confidence_for_tier(tier: int) -> float:
    return {0: 0.92, 1: 0.90, 2: 0.85, 3: 0.75}.get(tier, 0.65)
