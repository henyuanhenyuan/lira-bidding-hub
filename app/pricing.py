from __future__ import annotations

import math
from dataclasses import dataclass, field

from .contracts import Observation, PricePoint

# 缺失字段对不确定性的贡献
SPREAD_BASE = 0.005
SPREAD_COUPONS = 0.030
SPREAD_PROMOTIONS = 0.030
SPREAD_MEMBER = 0.020


def _coupon_saving(base: float, obs: Observation, missing: list[str]) -> float:
    if obs.coupons is None:
        missing.append("coupons")
        return 0.0
    stackable = 0.0
    best_single = 0.0
    for c in obs.coupons:
        if c.discount is None:
            continue
        if c.threshold is not None and base < c.threshold:
            continue
        if c.stackable:
            stackable += c.discount
        else:
            best_single = max(best_single, c.discount)
    return min(base, stackable + best_single)


def _promotion_saving(base: float, obs: Observation, missing: list[str]) -> float:
    if obs.promotions is None:
        missing.append("promotions")
        return 0.0
    total = 0.0
    for p in obs.promotions:
        if p.threshold is None or p.discount is None or p.threshold <= 0:
            continue
        if base < p.threshold:
            continue
        times = math.floor(base / p.threshold)
        if p.kind == "cross_store":
            total += times * p.discount
        else:
            total += p.discount
    return min(base, total)


def _coin_saving(base: float, obs: Observation, missing: list[str]) -> float:
    if obs.coin is None:
        missing.append("coin")
        return 0.0
    if obs.coin.rate <= 0:
        return 0.0
    return min(base * obs.coin.rate, obs.coin.cap)


def compute(
    target_id: str,
    ts: str,
    obs: Observation,
    source_tier: int,
) -> PricePoint | None:
    """标价 → 到手价区间。缺失显式记录，绝不用 0 填充。"""
    missing: list[str] = []

    if obs.list_price is None:
        return None

    base = float(obs.list_price)

    if obs.account_tier == "member":
        if obs.member_price is None:
            missing.append("member_price")
        else:
            base = min(base, obs.member_price)

    if obs.live_price is not None:
        base = min(base, obs.live_price)

    coupon = _coupon_saving(base, obs, missing)
    after_coupon = max(0.0, base - coupon)
    promo = _promotion_saving(after_coupon, obs, missing)
    after_promo = max(0.0, after_coupon - promo)
    coin = _coin_saving(after_promo, obs, missing)
    point = max(0.0, after_promo - coin)

    spread = SPREAD_BASE
    if "coupons" in missing:
        spread += SPREAD_COUPONS
    if "promotions" in missing:
        spread += SPREAD_PROMOTIONS
    if "member_price" in missing:
        spread += SPREAD_MEMBER
    if source_tier >= 3:
        spread += 0.010
    if source_tier >= 4:
        spread += 0.020

    confidence = 0.95
    confidence -= 0.12 * len(missing)
    if source_tier >= 3:
        confidence -= 0.08
    if source_tier >= 4:
        confidence -= 0.05
    confidence = max(0.20, min(0.95, confidence))

    return PricePoint(
        target_id=target_id,
        ts=ts,
        point=round(point, 2),
        price_low=round(point * (1 - spread), 2),
        price_high=round(point * (1 + spread), 2),
        confidence=round(confidence, 3),
        missing_fields=missing,
    )


# ---------------- 调价策略（确定性，模型只解释） ----------------

STRATEGIES = ("follow", "undercut", "match_band", "hold")


@dataclass
class PricePlan:
    """一次自主调价的确定性方案。"""

    action: str
    strategy: str
    from_price: float | None
    target_price: float | None
    floor_price: float | None
    delta_pct: float
    needs_review: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "strategy": self.strategy,
            "from_price": self.from_price,
            "target_price": self.target_price,
            "floor_price": self.floor_price,
            "delta_pct": round(self.delta_pct, 4),
            "needs_review": self.needs_review,
            "reasons": list(self.reasons),
        }


def floor_price(cost: float | None, margin_floor: float | None) -> float | None:
    """守住毛利率下限的最低可售价。"""
    if cost is None or margin_floor is None or margin_floor >= 1:
        return None
    return round(cost / (1 - margin_floor), 2)


def propose(
    point: PricePoint,
    my_price: float | None,
    cost: float | None,
    margin_floor: float | None,
    *,
    strategy: str = "follow",
    undercut_pct: float = 0.02,
    min_delta_pct: float = 0.005,
    max_delta_pct: float = 0.15,
) -> PricePlan:
    """根据竞品到手价给出目标价；只做确定性计算，越界显式标记复核。

    策略：
      follow      跟到竞品到手价
      undercut    在竞品到手价基础上下调 undercut_pct
      match_band  取竞品价格区间中值
      hold        维持我方价
    """
    if strategy not in STRATEGIES:
        strategy = "follow"

    if strategy == "hold":
        return PricePlan(
            action="hold", strategy=strategy, from_price=my_price,
            target_price=None, floor_price=floor_price(cost, margin_floor),
            delta_pct=0.0, needs_review=False, reasons=["策略为维持现价"],
        )

    if strategy == "undercut":
        raw = point.point * (1 - undercut_pct)
    elif strategy == "match_band":
        raw = (point.price_low + point.price_high) / 2
    else:
        raw = point.point

    reasons: list[str] = []
    needs_review = False
    lowest = floor_price(cost, margin_floor)
    target = raw
    if lowest is not None and target < lowest:
        target = lowest
        needs_review = True
        reasons.append(
            f"竞品到手价 {raw:.2f} 低于成本底线 {lowest:.2f}，按底线出价"
        )

    target = round(max(0.01, target), 2)
    if my_price is None:
        return PricePlan(
            action="adjust_price", strategy=strategy, from_price=None,
            target_price=target, floor_price=lowest, delta_pct=0.0,
            needs_review=True,
            reasons=["缺少我方价，只给出目标价，需人工确认"],
        )
    delta = (target - my_price) / my_price

    if abs(delta) > max_delta_pct:
        needs_review = True
        reasons.append(
            f"单次调价幅度 {delta:+.1%} 超过 {max_delta_pct:.0%} 阈值"
        )

    if abs(delta) < min_delta_pct:
        return PricePlan(
            action="hold", strategy=strategy, from_price=my_price,
            target_price=None, floor_price=lowest, delta_pct=delta,
            needs_review=False, reasons=["价差在死区内，不调价"],
        )

    return PricePlan(
        action="adjust_price", strategy=strategy, from_price=my_price,
        target_price=target, floor_price=lowest, delta_pct=delta,
        needs_review=needs_review, reasons=reasons,
    )
