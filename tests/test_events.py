from app import events
from app.contracts import PricePoint


def point(v, ts="2026-10-24T02:17:00+08:00", conf=0.87):
    return PricePoint(
        target_id="t1", ts=ts, point=v,
        price_low=v * 0.99, price_high=v * 1.01,
        confidence=conf, missing_fields=[],
    )


def run(cur, prev, tier=3, my_price=None, discontinuity=False):
    return events.detect(
        target_id="t1", snapshot_id="snap1", ts=cur.ts, source_tier=tier,
        point=cur, prev=prev, my_price=my_price, discontinuity=discontinuity,
    )


def test_small_change_no_event():
    out = run(point(299), point(297, ts="2026-10-23T02:17:00+08:00"))
    assert out == []


def test_ten_percent_drop_is_l2():
    out = run(point(269), point(299, ts="2026-10-23T02:17:00+08:00"))
    assert len(out) == 1
    assert out[0].type == "price_drop"
    assert out[0].severity == "L2"
    assert out[0].gate_level == "strong"


def test_l3_downgraded_for_low_tier_source():
    out = run(point(149), point(199, ts="2026-10-23T02:17:00+08:00"), tier=3)
    assert out[0].severity == "L2"
    assert "downgraded_by_tier" in out[0].note


def test_l3_allowed_for_official_tier():
    out = run(point(149), point(199, ts="2026-10-23T02:17:00+08:00"), tier=1)
    assert out[0].severity == "L3"


def test_band_breach_emitted():
    out = run(point(89), point(89, ts="2026-10-23T02:17:00+08:00"), my_price=100)
    types = [e.type for e in out]
    assert "band_breach" in types


def test_low_confidence_gates_to_observe():
    out = run(point(149, conf=0.40), point(199, ts="2026-10-23T02:17:00+08:00"), tier=1)
    assert out[0].gate_level == "observe"


def test_discontinuity_suppresses_delta():
    out = run(point(149), point(199, ts="2026-10-23T02:17:00+08:00"), discontinuity=True)
    assert len(out) == 1
    assert out[0].type == "source_switch"
    assert out[0].suppressed is True
