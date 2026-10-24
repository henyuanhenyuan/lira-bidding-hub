from __future__ import annotations

import math

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
