from __future__ import annotations

import json
from typing import Any

from . import db

SEVERITY_ORDER = {"L1": 1, "L2": 2, "L3": 3}
ALL_TOOLS = [
    "collection_health",
    "price_history",
    "search_cases",
    "search_docs",
    "my_product",
    "simulate_price",
    "get_event",
]

DEFAULT_SKILL = {
    "id": "default",
    "name": "通用研判",
    "description": "没有匹配到专用剧本时使用",
    "event_types": [],
    "min_severity": "L1",
    "playbook": "先确认数据可信，再看价格趋势与历史案例；不确认的动作一律先观察。",
    "allowed_tools": ALL_TOOLS,
    "version": 1,
    "enabled": 1,
}

BUILTIN = [
    {
        "id": "price_war",
        "name": "大促价格试探",
        "description": "降价/提价类事件：区分短期促销与结构性调价",
        "event_types": ["price_drop", "price_rise"],
        "min_severity": "L1",
        "playbook": (
            "先判断是短期促销还是结构性降价：查看近 30 天价格序列与历史案例。"
            "价差在 10% 以内优先考虑投券对冲；超过 20% 且连续两日未回调，"
            "再评估跟进。提价通常先观察，不急于跟进。"
        ),
        "allowed_tools": [
            "collection_health", "price_history", "search_cases", "search_docs",
            "my_product", "simulate_price",
        ],
    },
    {
        "id": "band_breach",
        "name": "价格带击穿",
        "description": "竞品长期低价击穿我方价格带",
        "event_types": ["band_breach"],
        "min_severity": "L1",
        "playbook": (
            "击穿价格带通常是引流款策略。先判断对方是否长期维持该价位，"
            "再评估正面跟价对主款毛利的伤害；优先考虑赠品、组合装或投券，"
            "而不是直接跟进到底价。"
        ),
        "allowed_tools": [
            "collection_health", "price_history", "search_cases", "search_docs",
            "my_product", "simulate_price",
        ],
    },
    {
        "id": "review_spike",
        "name": "评论异动",
        "description": "负面评论突增，寻找可攻击的体验缺口",
        "event_types": ["review_spike"],
        "min_severity": "L1",
        "playbook": (
            "先确认负面集中在哪个话题（物流、质量、价格、客服），"
            "再用规则文档确认平台对相关表述的约束；机会点必须能被事实支撑，"
            "不要拿单条极端评论当趋势。"
        ),
        "allowed_tools": [
            "collection_health", "search_cases", "search_docs", "my_product",
        ],
    },
]


def _row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "event_types": db.loads(row["event_types"], []),
        "min_severity": row["min_severity"],
        "playbook": row["playbook"],
        "allowed_tools": db.loads(row["allowed_tools"], []),
        "version": row["version"],
        "enabled": row["enabled"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def ensure_seeded(conn) -> None:
    for item in BUILTIN:
        exists = conn.execute("SELECT 1 FROM skill WHERE id = ?", (item["id"],)).fetchone()
        if exists:
            continue
        now = db.now_iso()
        conn.execute(
            "INSERT INTO skill (id, name, description, event_types, min_severity,"
            " playbook, allowed_tools, version, enabled, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                item["id"], item["name"], item["description"],
                json.dumps(item["event_types"], ensure_ascii=False),
                item["min_severity"], item["playbook"],
                json.dumps(item["allowed_tools"], ensure_ascii=False),
                1, 1, now, now,
            ),
        )


def list_skills(conn) -> list[dict[str, Any]]:
    ensure_seeded(conn)
    rows = conn.execute("SELECT * FROM skill ORDER BY id").fetchall()
    return [_row(row) for row in rows]


def pick_skill(conn, event_type: str, severity: str) -> dict[str, Any]:
    ensure_seeded(conn)
    level = SEVERITY_ORDER.get(severity, 1)
    candidates: list[dict[str, Any]] = []
    for row in conn.execute("SELECT * FROM skill WHERE enabled = 1").fetchall():
        skill = _row(row)
        if event_type not in skill["event_types"]:
            continue
        if level < SEVERITY_ORDER.get(skill["min_severity"] or "L1", 1):
            continue
        candidates.append(skill)
    if not candidates:
        return dict(DEFAULT_SKILL)
    candidates.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["min_severity"] or "L1", 1),
            item["version"],
        ),
        reverse=True,
    )
    return candidates[0]


def create_skill(
    conn,
    *,
    name: str,
    playbook: str,
    event_types: list[str],
    allowed_tools: list[str],
    description: str | None = None,
    min_severity: str = "L1",
    enabled: bool = True,
) -> dict[str, Any]:
    if not name.strip() or not playbook.strip():
        raise ValueError("name 和 playbook 不能为空")
    if min_severity not in SEVERITY_ORDER:
        raise ValueError("min_severity 只能是 L1/L2/L3")
    unknown = [item for item in allowed_tools if item not in ALL_TOOLS]
    if unknown:
        raise ValueError(f"未知工具：{', '.join(unknown)}")
    skill_id = db.new_id()
    now = db.now_iso()
    conn.execute(
        "INSERT INTO skill (id, name, description, event_types, min_severity, playbook,"
        " allowed_tools, version, enabled, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            skill_id, name.strip(), description,
            json.dumps(event_types, ensure_ascii=False), min_severity,
            playbook.strip(), json.dumps(allowed_tools, ensure_ascii=False),
            1, int(enabled), now, now,
        ),
    )
    row = conn.execute("SELECT * FROM skill WHERE id = ?", (skill_id,)).fetchone()
    return _row(row)


def update_skill(conn, skill_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    allowed = {"name", "description", "event_types", "min_severity", "playbook",
               "allowed_tools", "enabled"}
    updates = {key: value for key, value in changes.items() if key in allowed}
    if not updates:
        raise ValueError("没有可更新的字段")
    if "allowed_tools" in updates:
        unknown = [item for item in updates["allowed_tools"] if item not in ALL_TOOLS]
        if unknown:
            raise ValueError(f"未知工具：{', '.join(unknown)}")
    if "min_severity" in updates and updates["min_severity"] not in SEVERITY_ORDER:
        raise ValueError("min_severity 只能是 L1/L2/L3")

    sets = []
    params: list[Any] = []
    for key, value in updates.items():
        if key in ("event_types", "allowed_tools"):
            value = json.dumps(value, ensure_ascii=False)
        if key == "enabled":
            value = int(bool(value))
        sets.append(f"{key} = ?")
        params.append(value)
    sets.append("version = version + 1")
    sets.append("updated_at = ?")
    params.append(db.now_iso())
    params.append(skill_id)
    conn.execute(f"UPDATE skill SET {', '.join(sets)} WHERE id = ?", params)
    row = conn.execute("SELECT * FROM skill WHERE id = ?", (skill_id,)).fetchone()
    if not row:
        raise KeyError(skill_id)
    return _row(row)
