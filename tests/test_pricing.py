import pytest

from app.contracts import Coin, Coupon, Observation, Promotion
from app.pricing import compute


def pp(obs, tier=3):
    return compute("t1", "2026-10-24T02:17:00+08:00", obs, tier)


def test_basic_no_discounts():
    obs = Observation(list_price=299, coupons=[], promotions=[], coin=Coin(rate=0, cap=0))
    out = pp(obs)
    assert out is not None
    assert out.point == 299
    assert out.missing_fields == []
    assert out.confidence == pytest.approx(0.87)


def test_shop_coupon_applied():
    obs = Observation(
        list_price=299,
        coupons=[Coupon(kind="shop", threshold=299, discount=30)],
        promotions=None,
        coin=None,
    )
    out = pp(obs)
    assert out.point == 269
    assert "promotions" in out.missing_fields
    assert "coin" in out.missing_fields
    # 缺失两项 + 三级来源，置信度显著下降
    assert out.confidence < 0.70


def test_cross_store_promotion_multiplies():
    obs = Observation(
        list_price=600,
        coupons=[],
        promotions=[Promotion(kind="cross_store", threshold=300, discount=50)],
        coin=Coin(rate=0, cap=0),
    )
    out = pp(obs)
    assert out.point == 500


def test_member_price_wins():
    obs = Observation(
        list_price=299,
        member_price=250,
        account_tier="member",
        coupons=[],
        promotions=[],
        coin=Coin(rate=0, cap=0),
    )
    out = pp(obs)
    assert out.point == 250


def test_member_without_price_is_flagged_not_zeroed():
    obs = Observation(
        list_price=299,
        account_tier="member",
        coupons=[],
        promotions=[],
        coin=Coin(rate=0, cap=0),
    )
    out = pp(obs)
    assert out.point == 299
    assert "member_price" in out.missing_fields


def test_missing_list_price_returns_none():
    obs = Observation(list_price=None, coupons=[], promotions=[], coin=Coin(rate=0, cap=0))
    assert pp(obs) is None


def test_interval_brackets_point():
    obs = Observation(list_price=200, coupons=[], promotions=[], coin=Coin(rate=0, cap=0))
    out = pp(obs)
    assert out.price_low < out.point < out.price_high


def test_low_tier_reduces_confidence():
    obs = Observation(list_price=200, coupons=[], promotions=[], coin=Coin(rate=0, cap=0))
    high = compute("t", "ts", obs, 0)
    low = compute("t", "ts", obs, 3)
    assert high.confidence > low.confidence
