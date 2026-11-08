import pytest

from app import tools


def test_dev_mode_allows_without_secret(monkeypatch):
    monkeypatch.delenv("LIRA_MCP_SECRET", raising=False)
    tools.authorize_mcp()
    tools.authorize_mcp("anything")


def test_secret_requires_matching_token(monkeypatch):
    monkeypatch.setenv("LIRA_MCP_SECRET", "s3cret")
    monkeypatch.setenv("LIRA_MCP_TOKEN", "s3cret")
    tools.authorize_mcp()

    monkeypatch.setenv("LIRA_MCP_TOKEN", "wrong")
    with pytest.raises(tools.ToolPermissionError):
        tools.authorize_mcp()

    with pytest.raises(tools.ToolPermissionError):
        tools.authorize_mcp("")


def test_all_builtin_tools_are_read_only():
    for name in tools.TOOLS:
        assert tools.risk_of(name) == tools.RISK_READ


def test_unknown_tool_is_treated_as_irreversible():
    assert tools.risk_of("nope") == tools.RISK_IRREVERSIBLE
    assert tools.is_write_tool("nope") is True
