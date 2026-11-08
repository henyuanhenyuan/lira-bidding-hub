import json

from app import agent_graph
from app.llm.types import ChatResponse, Usage


def _decision(done=False, tool=None, args=None):
    return ChatResponse(
        text=json.dumps({"done": done, "tool": tool, "args": args or {}}),
        provider="fake", model="fake", usage=Usage(1, 1),
    )


def _state(**overrides):
    state = {
        "run_id": "react-run", "seq": 0, "tainted": False,
        "facts": {"title": "竞品A", "event_type": "price_drop", "severity": "L3"},
        "tool_results": [], "skill": {},
    }
    state.update(overrides)
    return state


def test_react_disabled_by_flag(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LOOP", "off")
    state = _state()
    assert agent_graph._react_node(state)["seq"] == 0


def test_react_noop_when_llm_unavailable(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LOOP", "on")
    monkeypatch.setattr(agent_graph.agent, "_llm_available", lambda: False)
    assert agent_graph._react_node(_state())["seq"] == 0


def test_react_stops_at_max_steps(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LOOP", "on")
    monkeypatch.setattr(agent_graph.agent, "_llm_available", lambda: True)
    monkeypatch.setattr(agent_graph.config, "AGENT_MAX_STEPS", 2)
    counter = {"n": 0}

    def fake_complete(*args, **kwargs):
        counter["n"] += 1
        return _decision(tool="price_history", args={"target_id": f"t{counter['n']}"})

    monkeypatch.setattr(agent_graph.llm, "complete", fake_complete)
    monkeypatch.setattr(
        agent_graph.tools, "call_tool", lambda name, args: {"ok": name}
    )
    result = agent_graph._react_node(_state())
    tool_calls = [item for item in result["tool_results"] if item["tool"] == "price_history"]
    assert len(tool_calls) == 2


def test_react_breaks_on_no_progress(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LOOP", "on")
    monkeypatch.setattr(agent_graph.agent, "_llm_available", lambda: True)
    monkeypatch.setattr(
        agent_graph.llm, "complete",
        lambda *a, **k: _decision(tool="price_history", args={"target_id": "t"}),
    )
    monkeypatch.setattr(
        agent_graph.tools, "call_tool", lambda name, args: {"ok": name}
    )
    result = agent_graph._react_node(_state())
    assert len([r for r in result["tool_results"] if r["tool"] == "price_history"]) == 1


def test_react_rejects_tool_outside_allowlist(monkeypatch):
    monkeypatch.setenv("LIRA_AGENT_LOOP", "on")
    monkeypatch.setattr(agent_graph.agent, "_llm_available", lambda: True)
    monkeypatch.setattr(
        agent_graph.llm, "complete",
        lambda *a, **k: _decision(tool="search_docs", args={"query": "x"}),
    )
    called = []
    monkeypatch.setattr(
        agent_graph.tools, "call_tool",
        lambda name, args: called.append(name) or {},
    )
    state = _state(skill={"allowed_tools": ["price_history"]})
    result = agent_graph._react_node(state)
    assert called == []
    assert result["tool_results"] == []
