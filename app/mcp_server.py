"""竞品情报工具层（MCP Server）。

启动：
    python -m app.mcp_server

外部 Agent（Claude Desktop / Cursor 等）可通过 stdio 连接本服务，
拿到与站内 Agent 完全相同的工具契约。

鉴权：设置 LIRA_MCP_SECRET 后，客户端进程必须提供相同的 LIRA_MCP_TOKEN。
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools

mcp = FastMCP("lira-competitor-tools")


def _call(name: str, args: dict[str, Any]) -> Any:
    tools.authorize_mcp()
    return tools.call_tool(name, args)


@mcp.tool()
def price_history(target_id: str, days: int = 30, limit: int = 60) -> dict:
    """读取竞品最近 N 天的到手价区间与置信度。"""
    return _call(
        "price_history", {"target_id": target_id, "days": days, "limit": limit}
    )


@mcp.tool()
def search_cases(
    query: str,
    event_type: str | None = None,
    price_band: str | None = None,
    delta_pct: float | None = None,
    limit: int = 3,
) -> dict:
    """检索历史相似案例，返回归因与 7 日结果。"""
    return _call(
        "search_cases",
        {
            "query": query,
            "event_type": event_type,
            "price_band": price_band,
            "delta_pct": delta_pct,
            "limit": limit,
        },
    )


@mcp.tool()
def search_docs(query: str, limit: int = 3) -> dict:
    """检索平台规则与内部策略文档切片，返回可引用的 doc:<id>。"""
    return _call("search_docs", {"query": query, "limit": limit})


@mcp.tool()
def my_product(target_id: str) -> dict:
    """读取我方对应 SKU 的价格、成本与毛利下限。"""
    return _call("my_product", {"target_id": target_id})


@mcp.tool()
def collection_health() -> dict:
    """读取采集新鲜度与各采集源滞后情况。"""
    return _call("collection_health", {})


@mcp.tool()
def simulate_price(target_id: str, new_price: float) -> dict:
    """模拟目标价下的毛利与护栏判定（只读推演，不落库）。"""
    return _call("simulate_price", {"target_id": target_id, "new_price": new_price})


@mcp.tool()
def get_event(event_id: str) -> dict:
    """读取一条事件的完整事实、证据 ID 与当时的价格点。"""
    return _call("get_event", {"event_id": event_id})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
