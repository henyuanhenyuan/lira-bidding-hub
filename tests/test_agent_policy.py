from app import agent
from app.contracts import PricePoint


def pt(v=269):
    return PricePoint(
        target_id="t1", ts="2026-10-24T02:17:00+08:00", point=v,
        price_low=v * 0.995, price_high=v * 1.005,
        confidence=0.87, missing_fields=[],
    )


def call(monkeypatch, llm_result, event_type="price_drop", severity="L3", gate="strong"):
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr(agent, "_call_llm", lambda facts, allowed: llm_result)
    return agent.analyze(
        event_type=event_type, severity=severity, gate=gate, title="竞品A",
        point=pt(), prev=None, allowed_evidence=["e1", "e2"],
    )


def test_llm_cannot_override_action_policy(monkeypatch):
    """模型可以决定怎么说，但不能决定做什么。"""
    fake = agent.Analysis(
        action="follow", confidence=0.9,
        narrative="模型建议直接跟价", evidence_ids=["e1"], generated_by="llm:test",
    )
    out = call(monkeypatch, fake)
    # L3 降价由确定性策略升级为自主调价，模型仍只负责措辞
    assert out.action == "adjust_price"
    assert out.narrative == "模型建议直接跟价"
    assert out.generated_by == "llm:test"


def test_llm_failure_falls_back_to_template(monkeypatch):
    out = call(monkeypatch, None)
    assert out.generated_by == "template:v1"
    assert out.evidence_ids == ["e1", "e2"]


def test_observe_gate_never_recommends_action(monkeypatch):
    fake = agent.Analysis(
        action="follow", confidence=0.9, narrative="x",
        evidence_ids=["e1"], generated_by="llm:test",
    )
    out = call(monkeypatch, fake, gate="observe")
    assert out.action == "no_action"
