from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# 只校验带单位的数字（价格/百分比/折扣），裸计数（如「7 天」）不参与，
# 否则正常文案会被误伤。
_TOKEN = re.compile(
    r"(?:(?P<cur>[¥$￥])\s*(?P<num1>\d[\d,]*(?:\.\d+)?))"
    r"|(?:(?P<num2>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|折|元|块))"
)


@dataclass(frozen=True)
class Violation:
    raw: str
    value: float


def _candidates(raw: str, unit: str) -> list[float]:
    value = float(raw.replace(",", ""))
    out = [value]
    if unit == "%":
        out.append(value / 100)
    elif unit == "折":
        out.append(value / 10)
    return out


def verify(
    text: str, *, allowed: Iterable[float], tolerance: float = 0.01
) -> list[Violation]:
    allowed_values = [float(value) for value in allowed]
    violations: list[Violation] = []
    for match in _TOKEN.finditer(text or ""):
        raw = match.group("num1") or match.group("num2")
        unit = "%" if match.group("cur") else (match.group("unit") or "")
        values = _candidates(raw, unit)
        if any(
            abs(candidate - value) <= tolerance
            for candidate in values
            for value in allowed_values
        ):
            continue
        violations.append(Violation(raw=match.group(0).strip(), value=values[0]))
    return violations


def facts_to_numbers(facts: dict[str, Any]) -> set[float]:
    numbers: set[float] = set()
    for key in ("price_low", "price_high", "confidence", "point", "prev_point"):
        value = facts.get(key)
        if isinstance(value, (int, float)):
            numbers.add(float(value))
    delta = facts.get("delta_pct")
    if isinstance(delta, (int, float)):
        numbers.add(float(delta))
        numbers.add(abs(float(delta)))
    for value in list(numbers):
        numbers.add(round(value * 100, 4))
        numbers.add(round(value, 2))
    return numbers
