from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

RERANK_URL = os.getenv("LIRA_RERANK_URL", "")
RERANK_MODEL = os.getenv("LIRA_RERANK_MODEL", "bge-reranker-v2-m3")
RERANK_TIMEOUT_S = float(os.getenv("LIRA_RERANK_TIMEOUT", "5"))

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


def _rule_rerank(
    cases: list[dict],
    *,
    query: str,
    price_band: str | None,
    delta_pct: float | None,
    limit: int,
) -> list[dict]:
    tokens = _tokens(query)
    ranked = sorted(
        cases,
        key=lambda c: -score(
            c, query_tokens=tokens, price_band=price_band, delta_pct=delta_pct
        ),
    )
    return ranked[:limit]


def _model_rerank(
    cases: list[dict], query: str, limit: int
) -> list[dict] | None:
    documents = [f"{c.get('summary', '')} {c.get('attribution', '')}" for c in cases]
    response = httpx.post(
        RERANK_URL,
        json={"model": RERANK_MODEL, "query": query, "documents": documents},
        timeout=RERANK_TIMEOUT_S,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("results") or payload.get("data") or []
    scored: list[tuple[dict, float]] = []
    for row in rows:
        index = row.get("index")
        value = row.get("relevance_score", row.get("score"))
        if index is None or value is None:
            continue
        scored.append((cases[int(index)], float(value)))
    if not scored:
        return None
    scored.sort(key=lambda pair: -pair[1])
    return [case for case, _ in scored[:limit]]


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
    if RERANK_URL:
        try:
            ranked = _model_rerank(cases, query, limit)
            if ranked:
                return ranked
        except Exception as exc:
            log.warning("reranker fallback to rules: %s", exc)
    return _rule_rerank(
        cases, query=query, price_band=price_band,
        delta_pct=delta_pct, limit=limit,
    )
