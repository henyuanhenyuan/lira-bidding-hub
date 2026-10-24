from app import guardrail


def test_ok_when_margin_above_floor():
    r = guardrail.evaluate(250, 180, 0.15)  # (250-180)/250 = 28%
    assert r.status == "ok"
    assert round(r.margin, 3) == 0.28


def test_blocked_when_margin_below_floor():
    r = guardrail.evaluate(89, 88, 0.15)  # 1.1%
    assert r.status == "blocked"
    assert "低于下限" in r.note


def test_warning_when_near_floor():
    r = guardrail.evaluate(210, 175, 0.15)  # 16.7%，落在缓冲带
    assert r.status == "warning"


def test_unknown_without_cost():
    r = guardrail.evaluate(200, None, 0.15)
    assert r.status == "unknown"
    assert r.margin is None


def test_no_price_change_is_ok():
    r = guardrail.evaluate(None, None, 0.15)
    assert r.status == "ok"
    assert "不改变价格" in r.note


def test_margin_helper():
    assert guardrail.margin_at(200, 150) == 0.25
    assert guardrail.margin_at(None, 150) is None
    assert guardrail.margin_at(200, None) is None
    assert guardrail.margin_at(0, 150) is None
