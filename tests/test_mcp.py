import asyncio

from mcp.shared.memory import create_connected_server_and_client_session

from app.mcp_server import mcp


def test_mcp_exposes_tools_and_calls_them():
    async def scenario():
        async with create_connected_server_and_client_session(
            mcp, raise_exceptions=True
        ) as session:
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            assert {
                "price_history",
                "search_cases",
                "my_product",
                "collection_health",
                "simulate_price",
                "get_event",
            } <= names

            result = await session.call_tool("collection_health", {})
            assert result.isError is False
            text = result.content[0].text
            assert "freshness" in text
            assert "collectors" in text

    asyncio.run(scenario())
