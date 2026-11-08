from app import approval


def _suggestion(action="hold", guardrail="ok"):
    return {"action": action, "guardrail": guardrail}


def test_price_changing_actions_are_high_risk():
    for action in ("adjust_coupon", "follow", "join_promo"):
        risk = approval.assess_risk(_suggestion(action))
        assert risk["level"] == "high"
        assert risk["roles"] == ("admin",)


def test_hold_is_normal_risk():
    risk = approval.assess_risk(_suggestion("hold"))
    assert risk["level"] == "normal"
    assert risk["roles"] == approval.APPROVER_ROLES


def test_blocked_guardrail_escalates():
    risk = approval.assess_risk(_suggestion("hold", guardrail="blocked"))
    assert risk["level"] == "high"


def test_strict_mode_flag(monkeypatch):
    monkeypatch.setenv("LIRA_HITL_STRICT", "on")
    assert approval._strict_hitl() is True
    monkeypatch.setenv("LIRA_HITL_STRICT", "off")
    assert approval._strict_hitl() is False
