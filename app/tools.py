from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import cases as case_store, collectors, db, docs as doc_store, guardrail


class ToolError(ValueError):
    """工具参数或执行错误。"""


RISK_READ = "read"
RISK_REVERSIBLE = "reversible_write"
RISK_IRREVERSIBLE = "irreversible_write"
RISK_LEVELS = (RISK_READ, RISK_REVERSIBLE, RISK_IRREVERSIBLE)
WRITE_RISKS = frozenset({RISK_REVERSIBLE, RISK_IRREVERSIBLE})


class ToolPermissionError(PermissionError):
    """工具权限不足（MCP 令牌缺失或越权调用）。"""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    risk: str = RISK_READ


def _require_str(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"{key} is required")
    return value.strip()


def _int_arg(args: dict, key: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(args.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{key} must be an integer") from exc
    return max(lo, min(hi, value))


def _float_arg(args: dict, key: str) -> float:
    try:
        value = float(args[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolError(f"{key} must be a number") from exc
    if value <= 0:
        raise ToolError(f"{key} must be positive")
    return value


def price_history(args: dict) -> dict:
    target_id = _require_str(args, "target_id")
    days = _int_arg(args, "days", 30, 1, 180)
    limit = _int_arg(args, "limit", 60, 1, 200)
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT ts, price_low, price_high, confidence, missing_fields"
            " FROM price_point WHERE target_id = ?"
            " AND datetime(ts) >= datetime('now', ?)"
            " ORDER BY ts DESC LIMIT ?",
            (target_id, f"-{days} days", limit),
        ).fetchall()
    points = [
        {**dict(row), "missing_fields": db.loads(row["missing_fields"], [])}
        for row in rows
    ]
    return {"target_id": target_id, "days": days, "count": len(points), "points": points}


def search_cases(args: dict) -> dict:
    query = _require_str(args, "query")
    event_type = args.get("event_type") or None
    price_band = args.get("price_band") or None
    delta_pct = args.get("delta_pct")
    limit = _int_arg(args, "limit", 3, 1, 10)
    if delta_pct is not None:
        try:
            delta_pct = float(delta_pct)
        except (TypeError, ValueError) as exc:
            raise ToolError("delta_pct must be a number") from exc
    with db.get_db() as conn:
        found = case_store.search(
            conn,
            query=query[:200],
            category=None,
            event_type=event_type,
            price_band=price_band,
            delta_pct=delta_pct,
            limit=limit,
        )
    return {"query": query, "count": len(found), "cases": [c.as_dict() for c in found]}


def search_docs(args: dict) -> dict:
    query = _require_str(args, "query")
    limit = _int_arg(args, "limit", 3, 1, 10)
    with db.get_db() as conn:
        found = doc_store.search_docs(conn, query[:200], limit)
    return {"query": query, "count": len(found), "chunks": found}


def my_product(args: dict) -> dict:
    target_id = _require_str(args, "target_id")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT t.id, t.title, t.my_sku, t.my_price, p.title AS product_title,"
            " p.price AS product_price, p.cost, p.margin_floor"
            " FROM target t LEFT JOIN my_product p ON p.sku = t.my_sku"
            " WHERE t.id = ?",
            (target_id,),
        ).fetchone()
    if not row:
        raise ToolError(f"target not found: {target_id}")
    return {
        "target_id": row["id"],
        "title": row["title"],
        "sku": row["my_sku"],
        "my_price": row["my_price"],
        "product_title": row["product_title"],
        "product_price": row["product_price"],
        "cost": row["cost"],
        "margin_floor": row["margin_floor"],
        "configured": bool(row["my_sku"]),
    }


def collection_health(_: dict) -> dict:
    with db.get_db() as conn:
        return {
            "freshness": collectors.freshness(conn),
            "collectors": collectors.health(conn),
        }


def simulate_price(args: dict) -> dict:
    target_id = _require_str(args, "target_id")
    new_price = _float_arg(args, "new_price")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT t.my_price, p.cost, p.margin_floor"
            " FROM target t LEFT JOIN my_product p ON p.sku = t.my_sku"
            " WHERE t.id = ?",
            (target_id,),
        ).fetchone()
    if not row:
        raise ToolError(f"target not found: {target_id}")
    floor = row["margin_floor"] if row["margin_floor"] is not None else 0.15
    result = guardrail.evaluate(new_price, row["cost"], floor)
    my_price = row["my_price"]
    return {
        "target_id": target_id,
        "new_price": round(new_price, 2),
        "my_price": my_price,
        "cost": row["cost"],
        "delta_vs_my_price": (
            round(new_price - my_price, 2) if my_price is not None else None
        ),
        **result.as_dict(),
    }


def get_event(args: dict) -> dict:
    event_id = _require_str(args, "event_id")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT e.*, t.title AS target_title, t.my_price"
            " FROM event e LEFT JOIN target t ON t.id = e.target_id"
            " WHERE e.id = ?",
            (event_id,),
        ).fetchone()
        if not row:
            raise ToolError(f"event not found: {event_id}")
        point = conn.execute(
            "SELECT ts, price_low, price_high, confidence, missing_fields"
            " FROM price_point WHERE target_id = ? AND ts = ?",
            (row["target_id"], row["ts"]),
        ).fetchone()
    result = dict(row)
    result["evidence"] = db.loads(row["evidence"], [])
    result["price_point"] = (
        {**dict(point), "missing_fields": db.loads(point["missing_fields"], [])}
        if point
        else None
    )
    return result


TOOLS: dict[str, Tool] = {
    "price_history": Tool(
        name="price_history",
        description="读取竞品最近 N 天的到手价区间与置信度，用于判断是短期波动还是结构性变化。",
        input_schema={
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "竞品目标 ID"},
                "days": {"type": "integer", "minimum": 1, "maximum": 180, "default": 30},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 60},
            },
            "required": ["target_id"],
        },
        handler=price_history,
    ),
    "search_cases": Tool(
        name="search_cases",
        description="检索历史相似案例（向量 + 关键词 + 重排），返回归因与 7 日结果，供本次研判引用。",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索语句，例如标题+事件说明"},
                "event_type": {"type": "string"},
                "price_band": {"type": "string", "description": "如 250-300"},
                "delta_pct": {"type": "number"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
            "required": ["query"],
        },
        handler=search_cases,
    ),
    "search_docs": Tool(
        name="search_docs",
        description="检索平台规则、活动玩法与内部策略文档切片，返回可引用的 doc:<id>。",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索语句，例如活动规则、价保政策"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
            "required": ["query"],
        },
        handler=search_docs,
    ),
    "my_product": Tool(
        name="my_product",
        description="读取我方对应 SKU 的价格、成本与毛利下限，用于毛利护栏判断。",
        input_schema={
            "type": "object",
            "properties": {"target_id": {"type": "string"}},
            "required": ["target_id"],
        },
        handler=my_product,
    ),
    "collection_health": Tool(
        name="collection_health",
        description="读取采集新鲜度与各采集源滞后情况，用于判断本次事实是否可信。",
        input_schema={"type": "object", "properties": {}},
        handler=collection_health,
    ),
    "simulate_price": Tool(
        name="simulate_price",
        description="模拟一个目标价下的毛利与护栏判定，不写库、不做决策。",
        input_schema={
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "new_price": {"type": "number", "minimum": 0.01},
            },
            "required": ["target_id", "new_price"],
        },
        handler=simulate_price,
    ),
    "get_event": Tool(
        name="get_event",
        description="读取一条事件的完整事实、证据 ID 与当时的价格点。",
        input_schema={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
        handler=get_event,
    ),
}


def list_tools() -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in TOOLS.values()
    ]


def call_tool(name: str, args: dict[str, Any] | None = None) -> Any:
    tool = TOOLS.get(name)
    if not tool:
        raise ToolError(f"unknown tool: {name}")
    payload = args or {}
    if not isinstance(payload, dict):
        raise ToolError("arguments must be an object")
    return tool.handler(payload)


def risk_of(name: str) -> str:
    tool = TOOLS.get(name)
    return tool.risk if tool else RISK_IRREVERSIBLE


def is_write_tool(name: str) -> bool:
    return risk_of(name) in WRITE_RISKS


def read_only(names: list[str]) -> list[str]:
    return [name for name in names if not is_write_tool(name)]


def authorize_mcp(token: str | None = None) -> None:
    """MCP stdio 服务的静态令牌校验。

    - 未配置 LIRA_MCP_SECRET：开发模式，放行；
    - 配置后必须提供与之相等的 LIRA_MCP_TOKEN。
    """
    import os

    secret = os.getenv("LIRA_MCP_SECRET", "").strip()
    if not secret:
        return
    provided = token if token is not None else os.getenv("LIRA_MCP_TOKEN", "")
    if provided != secret:
        raise ToolPermissionError("MCP 令牌无效或缺失")
