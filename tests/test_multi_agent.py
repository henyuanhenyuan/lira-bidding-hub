from app import agent_graph


def _state(**kwargs):
    run_id = agent_graph._new_run("e-test", "unit")
    return {"run_id": run_id, "event_id": "e-test", "seq": 0, **kwargs}


def _health(stale: bool) -> list[dict]:
    return [
        {
            "tool": "collection_health",
            "status": "ok",
            "result": {"freshness": {"stale": stale}},
        }
    ]


def test_steward_downgrades_stale_l3(monkeypatch):
    monkeypatch.setenv("LIRA_STEWARD_ENFORCE", "on")
    state = _state(
        facts={"severity": "L3", "event_type": "price_drop"},
        tool_results=_health(stale=True),
    )
    out = agent_graph._steward_node(state)
    assert out["facts"]["severity"] == "L2"
    assert out["facts"]["downgraded_by_freshness"] is True


def test_steward_keeps_l3_when_enforce_off(monkeypatch):
    monkeypatch.delenv("LIRA_STEWARD_ENFORCE", raising=False)
    state = _state(
        facts={"severity": "L3", "event_type": "price_drop"},
        tool_results=_health(stale=True),
    )
    out = agent_graph._steward_node(state)
    assert out["facts"]["severity"] == "L3"
    assert not out["facts"].get("downgraded_by_freshness")


def test_steward_keeps_l3_when_data_fresh(monkeypatch):
    monkeypatch.setenv("LIRA_STEWARD_ENFORCE", "on")
    state = _state(
        facts={"severity": "L3", "event_type": "price_drop"},
        tool_results=_health(stale=False),
    )
    out = agent_graph._steward_node(state)
    assert out["facts"]["severity"] == "L3"


def test_risk_computes_target_price_for_follow():
    state = _state(
        facts={"point": 199.0, "my_price": 299.0, "cost": 100.0, "margin_floor": 0.15},
        analysis={"action": "follow"},
    )
    out = agent_graph._risk_node(state)
    assert out["risk"]["target_price"] == 199.0
    assert out["risk"]["guardrail"]["status"] == "ok"


def test_risk_skips_target_price_for_hold():
    state = _state(
        facts={"point": 199.0, "my_price": 299.0, "cost": 100.0, "margin_floor": 0.15},
        analysis={"action": "hold"},
    )
    out = agent_graph._risk_node(state)
    assert out["risk"]["target_price"] is None


def test_writer_builds_proposal():
    state = _state(
        facts={"price_low": 197.0, "price_high": 201.0, "my_price": 299.0},
        analysis={"action": "adjust_coupon", "narrative": "建议先投券"},
        risk={"target_price": 199.0},
    )
    out = agent_graph._writer_node(state)
    assert out["proposal"]["impact_low"] == 98.0
    assert out["proposal"]["impact_high"] == 102.0
    assert out["proposal"]["narrative"] == "建议先投券"
    assert out["proposal"]["target_price"] == 199.0


def test_stages_default_to_full_pipeline():
    from app import skills

    assert agent_graph._stages({"skill": None}) == set(skills.DEFAULT_STAGES)
    custom = {"skill": {"stages": ["planning", "tools", "analyst"]}}
    assert agent_graph._stages(custom) == {"planning", "tools", "analyst"}
