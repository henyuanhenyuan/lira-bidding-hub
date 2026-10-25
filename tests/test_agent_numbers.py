import json

from app import agent
from app.contracts import PricePoint


def _point(value: float = 269.0) -> PricePoint:
    return PricePoint(
        target_id="t1", ts="2026-10-24T02:17:00+08:00", point=value,
        price_low=value * 0.995, price_high=value * 1.005,
        confidence=0.87, missing_fields=[],
    )


def _fake_payload(narrative: str) -> dict:
    return {
        "message": {
            "content": json.dumps(
                {
                    "action": "hold",
                    "confidence": 0.6,
                    "evidence_ids": ["snap:1"],
                    "narrative": narrative,
                },
                ensure_ascii=False,
            )
        }
    }


def _run(monkeypatch, narrative: str):
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr(agent, "_post_chat", lambda body: _fake_payload(narrative))
    return agent.analyze(
        event_type="price_drop", severity="L2", gate="strong", title="竞品A",
        point=_point(), prev=None, allowed_evidence=["snap:1"],
    )


def test_matching_number_is_kept(monkeypatch):
    out = _run(monkeypatch, "到手价约 269 元，建议先观察。")
    assert out.generated_by.startswith("llm")
    assert "269" in out.narrative


def test_invented_number_falls_back_to_template(monkeypatch):
    out = _run(monkeypatch, "竞品降到了 999 元，建议跟进。")
    assert out.generated_by.startswith("template")
    assert "999" not in out.narrative


def test_bare_count_does_not_trigger_fallback(monkeypatch):
    out = _run(monkeypatch, "7 天内可申请价保，建议先观察。")
    assert out.generated_by.startswith("llm")
