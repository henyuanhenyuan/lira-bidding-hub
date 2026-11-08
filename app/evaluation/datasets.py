"""金标评测集：从 JSONL 加载、按 tier 选择、写入 eval_case 表。

金标文件随代码发布（`app/evaluation/golden/`），不依赖 tests 目录。
期望值按 README 与 config 中的业务规则推导，不读取被测实现。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db

GOLDEN_DIR = Path(__file__).with_name("golden")
AGENT_CASES = GOLDEN_DIR / "agent_cases.jsonl"
RAG_CASES = GOLDEN_DIR / "rag_cases.jsonl"

TIERS: dict[str, tuple[str, ...]] = {
    "smoke": ("easy",),
    "core": ("easy", "medium"),
    "full": ("easy", "medium", "hard"),
}

REQUIRED_FIELDS = (
    "name", "segment", "difficulty", "expected_action",
    "expected_event_type", "payload",
)


@dataclass(frozen=True)
class GoldenCase:
    name: str
    segment: str
    difficulty: str
    expected_action: str
    expected_event_type: str
    payload: dict[str, Any]
    expected_chunks: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    @property
    def note(self) -> str:
        return self.notes or f"{self.segment}/{self.difficulty}"


def _parse(raw: dict[str, Any], line_no: int) -> GoldenCase:
    missing = [key for key in REQUIRED_FIELDS if key not in raw]
    if missing:
        raise ValueError(f"金标第 {line_no} 行缺少字段：{', '.join(missing)}")
    payload = raw["payload"]
    if not isinstance(payload, dict) or "snapshots" not in payload:
        raise ValueError(f"金标「{raw['name']}」的 payload 必须包含 snapshots")
    return GoldenCase(
        name=str(raw["name"]),
        segment=str(raw["segment"]),
        difficulty=str(raw["difficulty"]),
        expected_action=str(raw["expected_action"]),
        expected_event_type=str(raw["expected_event_type"]),
        payload=payload,
        expected_chunks=tuple(raw.get("expected_chunks") or ()),
        notes=str(raw.get("notes") or ""),
    )


def load(path: Path | None = None) -> list[GoldenCase]:
    """读取金标文件；同名用例保留第一条。"""
    target = path or AGENT_CASES
    if not target.exists():
        raise FileNotFoundError(f"金标文件不存在：{target}")
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    with target.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            case = _parse(json.loads(text), line_no)
            if case.name in seen:
                raise ValueError(f"金标用例重名：{case.name}")
            seen.add(case.name)
            cases.append(case)
    return cases


def select(cases: list[GoldenCase], tier: str) -> list[GoldenCase]:
    if tier not in TIERS:
        raise ValueError(f"未知 tier：{tier}（可选 {', '.join(TIERS)}）")
    allowed = set(TIERS[tier])
    return [case for case in cases if case.difficulty in allowed]


def by_name(cases: list[GoldenCase]) -> dict[str, GoldenCase]:
    return {case.name: case for case in cases}


def seed(conn, cases: list[GoldenCase]) -> int:
    """把金标写入 eval_case：新用例插入，已有用例以金标文件为准更新。"""
    rows = conn.execute(
        "SELECT name, expected_action, expected_event_type, payload, notes"
        " FROM eval_case"
    ).fetchall()
    existing = {row["name"]: row for row in rows}
    inserted = 0
    for case in cases:
        payload = json.dumps(case.payload, ensure_ascii=False)
        row = existing.get(case.name)
        if row is not None:
            if (
                row["expected_action"] != case.expected_action
                or row["expected_event_type"] != case.expected_event_type
                or row["payload"] != payload
                or row["notes"] != case.note
            ):
                conn.execute(
                    "UPDATE eval_case SET payload = ?, expected_action = ?,"
                    " expected_event_type = ?, notes = ? WHERE name = ?",
                    (
                        payload, case.expected_action, case.expected_event_type,
                        case.note, case.name,
                    ),
                )
            continue
        conn.execute(
            "INSERT INTO eval_case (id, name, payload, expected_action,"
            " expected_event_type, notes, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                db.new_id(), case.name, payload,
                case.expected_action, case.expected_event_type,
                case.note, db.now_iso(),
            ),
        )
        inserted += 1
    return inserted
