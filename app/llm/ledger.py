"""成本账本：按模型单价把 token 折算成金额。

单价单位：元 / 千 token（prompt, completion）。可用 LIRA_PRICE_TABLE 覆盖：
{"qwen-plus": [0.0008, 0.002]}
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "qwen-plus": (0.0008, 0.002),
    "qwen-max": (0.0024, 0.0096),
    "qwen-turbo": (0.0003, 0.0006),
    "deepseek-chat": (0.001, 0.002),
    "deepseek-reasoner": (0.004, 0.016),
    "gpt-4o-mini": (0.0011, 0.0044),
}

FREE_MODELS = ("qwen3", "llama", "mistral", "ollama")


def _price_table() -> dict[str, tuple[float, float]]:
    raw = os.getenv("LIRA_PRICE_TABLE", "").strip()
    if not raw:
        return DEFAULT_PRICES
    try:
        parsed = json.loads(raw)
        return {key: (float(v[0]), float(v[1])) for key, v in parsed.items()}
    except (ValueError, TypeError, IndexError):
        return DEFAULT_PRICES


def price_of(model: str) -> tuple[float, float]:
    table = _price_table()
    if model in table:
        return table[model]
    for prefix in FREE_MODELS:
        if model.startswith(prefix):
            return (0.0, 0.0)
    return (0.0, 0.0)


def cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = price_of(model)
    value = (
        (prompt_tokens or 0) / 1000 * prompt_price
        + (completion_tokens or 0) / 1000 * completion_price
    )
    return round(value, 6)


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    total = sum(float(row.get("cost") or 0) for row in rows)
    return {"cost": round(total, 6), "calls": len(rows)}
