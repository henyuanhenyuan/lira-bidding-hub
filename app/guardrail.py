from __future__ import annotations

from dataclasses import dataclass

# 距离毛利率下限的安全缓冲，进入缓冲带给出警告
BUFFER = 0.05


@dataclass
class GuardrailResult:
    status: str  # ok | warning | blocked | unknown
    margin: float | None
    floor: float | None
    note: str

    def as_dict(self) -> dict:
        return {
            "guardrail": self.status,
            "margin_at_target": None if self.margin is None else round(self.margin, 4),
            "margin_floor": self.floor,
            "guardrail_note": self.note,
        }


def margin_at(price: float | None, cost: float | None) -> float | None:
    if not price or cost is None or price <= 0:
        return None
    return (price - cost) / price


def evaluate(
    proposed_price: float | None,
    cost: float | None,
    floor: float | None,
) -> GuardrailResult:
    """目标价必须守住毛利率下限；没有成本数据时不允许放行。"""
    if proposed_price is None:
        return GuardrailResult("ok", None, floor, "不改变价格")

    if cost is None or floor is None:
        return GuardrailResult(
            "unknown", None, floor, "未设置成本价，无法校验毛利，需人工审批"
        )

    m = margin_at(proposed_price, cost)
    assert m is not None

    if proposed_price <= 0:
        return GuardrailResult("blocked", m, floor, "目标价非法")
    if m < floor:
        return GuardrailResult(
            "blocked", m, floor,
            f"目标价 {proposed_price:.2f} 的毛利率 {m:.1%} 低于下限 {floor:.1%}",
        )
    if m < floor + BUFFER:
        return GuardrailResult(
            "warning", m, floor,
            f"毛利率 {m:.1%} 接近下限 {floor:.1%}，需审批确认",
        )
    return GuardrailResult("ok", m, floor, f"毛利率 {m:.1%}，高于下限 {floor:.1%}")
