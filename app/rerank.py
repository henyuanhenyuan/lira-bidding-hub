from __future__ import annotations

import re
from datetime import datetime, timezone

_TOKEN = re.compile(r"[a-zA-Z0-9]+|[一-龥]{2}")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _recency(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).days
    return max(0.0, 1.0 - days / 540)  # 一年半线性衰减


def score(
    case: dict,
    *,
    query_tokens: set[str],
    price_band: str | None,
    delta_pct: float | None,
) -> float:
    """轻量重排：词面重叠 + 价格带 + 幅度接近 + 时效。不引入模型。"""
    text = f"{case.get('summary', '')} {case.get('attribution', '')}"
    overlap = len(query_tokens & _tokens(text)) / (len(query_tokens) or 1)

    band_bonus = 1.0 if (price_band and case.get("price_band") == price_band) else 0.0

    delta_bonus = 0.0
    if delta_pct is not None and case.get("delta_pct") is not None:
        gap = abs(abs(case["delta_pct"]) - abs(delta_pct))
        delta_bonus = max(0.0, 1.0 - gap / 0.3)

    return (
        0.45 * overlap
        + 0.25 * band_bonus
        + 0.20 * delta_bonus
        + 0.10 * _recency(case.get("ts"))
    )


def rerank(
    cases: list[dict],
    *,
    query: str,
    price_band: str | None,
    delta_pct: float | None,
    limit: int = 3,
) -> list[dict]:
    if not cases:
        return []
    tokens = _tokens(query)
    ranked = sorted(
        cases,
        key=lambda c: -score(
            c, query_tokens=tokens, price_band=price_band, delta_pct=delta_pct
        ),
    )
    return ranked[:limit]
