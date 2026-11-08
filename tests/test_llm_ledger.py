from app.llm import ledger
from app.prompts import registry


def test_paid_model_cost():
    assert ledger.cost("qwen-plus", 1000, 1000) == 0.0028
    assert ledger.cost("deepseek-chat", 0, 1000) == 0.002


def test_local_model_is_free():
    assert ledger.cost("qwen3:14b", 10000, 10000) == 0.0
    assert ledger.cost("unknown-model", 1000, 1000) == 0.0


def test_price_table_override(monkeypatch):
    monkeypatch.setenv("LIRA_PRICE_TABLE", '{"custom": [1, 2]}')
    assert ledger.cost("custom", 1000, 1000) == 3.0


def test_prompt_registry_binds_existing_text():
    from app import agent

    spec = registry.get("analysis")
    assert spec.text == agent.PROMPT
    assert spec.schema is agent.OUTPUT_SCHEMA
    assert registry.version_of("analysis") == "analysis-v1"
    assert registry.version_of("nope") == "unknown"
