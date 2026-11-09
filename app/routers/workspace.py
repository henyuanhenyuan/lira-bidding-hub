from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import agent, auth, db, llm
from .. import retrieval_service

router = APIRouter()


def _parse_ts(value: str) -> str:
    return (value or "")[:10]


def _parse_chat(text: str) -> dict[str, Any]:
    import json as _json

    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        return _json.loads(text[start:end + 1])
    except ValueError:
        return {}


def _remember(question: str, result: dict[str, Any]) -> None:
    if len(_CHAT_CACHE) >= CHAT_CACHE_SIZE:
        _CHAT_CACHE.pop(next(iter(_CHAT_CACHE)))
    _CHAT_CACHE[question] = result


@router.get("/api/dashboard")
def dashboard(days: int = 7) -> dict[str, Any]:
    """工作区与大屏共用的聚合数据：竞价对比、事件趋势、处置状态。"""
    days = max(1, min(30, days))
    with db.get_db() as conn:
        targets = [
            dict(row) for row in conn.execute(
                "SELECT id, title, platform, my_price, my_sku, active"
                " FROM target WHERE active = 1 ORDER BY title"
            ).fetchall()
        ]
        points = conn.execute(
            "SELECT target_id, ts, price_low, price_high FROM ("
            "  SELECT target_id, ts, price_low, price_high,"
            "         row_number() OVER (PARTITION BY target_id ORDER BY ts DESC) AS rn"
            "  FROM price_point"
            ") ranked WHERE rn <= 2 ORDER BY ts DESC"
        ).fetchall()
        events = [
            dict(row) for row in conn.execute(
                "SELECT id, target_id, ts, type, severity FROM event"
                " WHERE suppressed = 0 ORDER BY ts DESC LIMIT 500"
            ).fetchall()
        ]
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM suggestion GROUP BY status"
        ).fetchall()

    by_target: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        bucket = by_target.setdefault(point["target_id"], [])
        if len(bucket) < 2:
            bucket.append(dict(point))

    compare = []
    for target in targets:
        history = by_target.get(target["id"], [])
        latest = history[0] if history else None
        prev = history[1] if len(history) > 1 else None
        latest_mid = None
        delta = None
        if latest:
            latest_mid = round((latest["price_low"] + latest["price_high"]) / 2, 2)
            if prev:
                prev_mid = (prev["price_low"] + prev["price_high"]) / 2
                if prev_mid:
                    delta = round((latest_mid - prev_mid) / prev_mid, 4)
        severity = next(
            (event["severity"] for event in events if event["target_id"] == target["id"]),
            None,
        )
        compare.append(
            {
                **target,
                "point": latest_mid,
                "price_low": latest["price_low"] if latest else None,
                "price_high": latest["price_high"] if latest else None,
                "delta": delta,
                "severity": severity,
                "last_ts": latest["ts"] if latest else None,
            }
        )

    trend: dict[str, int] = {}
    severity: dict[str, int] = {}
    for event in events:
        day = _parse_ts(event["ts"])
        trend[day] = trend.get(day, 0) + 1
        severity[event["severity"]] = severity.get(event["severity"], 0) + 1

    ordered_days = sorted(trend)[-days:]
    return {
        "compare": compare,
        "trend": [{"date": day, "count": trend[day]} for day in ordered_days],
        "severity": severity,
        "status": {row["status"]: row["n"] for row in status_rows},
        "generated_at": db.now_iso(),
    }


CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer"],
}

INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {"insights": {"type": "array", "items": {"type": "string"}}},
    "required": ["insights"],
}

_INSIGHT_CACHE: dict[str, Any] = {"signature": "", "at": 0.0, "value": None}
INSIGHT_TTL = 300.0

_CHAT_CACHE: dict[str, dict[str, Any]] = {}
CHAT_CACHE_SIZE = 64


class ChatIn(BaseModel):
    question: str
    limit: int = 4


@router.post("/api/agent/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    """工作区内嵌小问答：检索知识库后回答，并返回引用。"""
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    cached = _CHAT_CACHE.get(question)
    if cached is not None:
        return {**cached, "cached": True}

    with db.get_db() as conn:
        chunks = retrieval_service.search_docs(
            conn, question[:200], max(1, min(6, body.limit)), rewrite_llm=False
        )

    citations = [
        {
            "id": item.get("id"),
            "title": item.get("doc_title"),
            "score": item.get("score"),
            "content": str(item.get("content") or "")[:160],
        }
        for item in chunks
    ]

    if agent._llm_available() and chunks:
        context = "\n".join(
            f"[{index}] {item.get('content')}"
            for index, item in enumerate(chunks, start=1)
        )
        response = llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "只依据给定资料直接回答，不要复述问题、不要输出思考过程，"
                        "不超过 120 字。输出 JSON："
                        '{"answer": "...", "citations": [用到的资料编号]}。'
                    ),
                },
                {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
            ],
            kind="chat",
            prompt_name="analysis",
            schema=CHAT_SCHEMA,
            max_tokens=220,
            temperature=0.1,
        )
        if response and response.text.strip():
            payload = _parse_chat(response.text)
            used = [
                {
                    **citation,
                    "index": index,
                }
                for index, citation in enumerate(citations, start=1)
            ]
            cited = payload.get("citations") if isinstance(payload, dict) else None
            if isinstance(cited, list):
                used = [
                    item for item in used
                    if item["index"] in {int(value) for value in cited if str(value).isdigit()}
                ] or used
            answer_text = (
                payload.get("answer") if isinstance(payload, dict) else None
            ) or response.text.strip()
            result = {"answer": answer_text, "citations": used, "mode": "llm"}
            _remember(question, result)
            return result

    if not chunks:
        return {"answer": "知识库里没有找到相关规则。", "citations": [], "mode": "empty"}

    answer = "根据知识库：\n" + "\n".join(
        f"{index}. {str(item.get('content') or '')[:120]}"
        for index, item in enumerate(chunks[:3], start=1)
    )
    result = {
        "answer": answer,
        "citations": [
            {**citation, "index": index}
            for index, citation in enumerate(citations, start=1)
        ],
        "mode": "extractive",
    }
    _remember(question, result)
    return result


def _rule_insights(dash: dict[str, Any]) -> list[str]:
    compare = dash.get("compare") or []
    insights: list[str] = []
    breaches = [
        item for item in compare
        if item.get("my_price") and item.get("point")
        and item["point"] < item["my_price"] * 0.95
    ]
    if breaches:
        names = "、".join(item["title"] for item in breaches[:3])
        insights.append(f"{len(breaches)} 个竞品已击穿我方价格带：{names}，建议优先处置。")
    drops = [
        item for item in compare
        if item.get("delta") is not None and item["delta"] <= -0.10
    ]
    if drops:
        worst = min(drops, key=lambda item: item["delta"])
        insights.append(
            f"{worst['title']} 近期降幅 {abs(worst['delta']) * 100:.0f}%，是当前最激进的价格动作。"
        )
    l3 = (dash.get("severity") or {}).get("L3", 0)
    if l3:
        insights.append(f"有 {l3} 条 L3 事件待研判，建议先看数据新鲜度再决策。")
    if not insights:
        insights.append("市场暂无明显价格异动，保持监控即可。")
    return insights[:3]


@router.get("/api/agent/insights")
def insights(days: int = 7) -> dict[str, Any]:
    """AI 实时解读市场数据；无模型时用规则兜底。5 分钟缓存。"""
    dash = dashboard(days)
    signature = "|".join(
        [
            str(len(dash["compare"])),
            str(sum(dash["severity"].values())),
            str(dash["trend"][-1] if dash["trend"] else ""),
        ]
    )
    now = time.time()
    if (
        _INSIGHT_CACHE["value"] is not None
        and _INSIGHT_CACHE["signature"] == signature
        and now - _INSIGHT_CACHE["at"] < INSIGHT_TTL
    ):
        return {**_INSIGHT_CACHE["value"], "cached": True}

    compact = {
        "targets": [
            {
                "title": item["title"], "my_price": item["my_price"],
                "point": item["point"], "delta": item["delta"],
                "severity": item["severity"],
            }
            for item in dash["compare"][:12]
        ],
        "severity": dash["severity"],
        "trend": dash["trend"],
    }
    result: dict[str, Any] = {"mode": "rule", "insights": _rule_insights(dash)}

    if agent._llm_available():
        response = llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "你是竞品定价分析师。基于给定数据写 3 条中文洞察，"
                        "每条不超过 40 字，必须点名具体竞品并带数字，"
                        "不要空话。示例：\"竞品A 到手价 219 元，较上次降 12%，已贴近我方价格带。\" "
                        '输出 JSON：{"insights": ["第一条", "第二条", "第三条"]}'
                    ),
                },
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
            ],
            kind="insights",
            prompt_name="analysis",
            schema=INSIGHTS_SCHEMA,
            max_tokens=220,
            temperature=0.2,
        )
        if response and response.text.strip():
            payload = _parse_chat(response.text)
            values = payload.get("insights") if isinstance(payload, dict) else None
            cleaned = [
                str(item).strip()[:80]
                for item in (values or [])
                if len(str(item).strip()) >= 8 and str(item).strip(" .…") != ""
            ]
            if len(cleaned) >= 2:
                result = {"mode": "llm", "insights": cleaned[:4]}
            else:
                result = {**result, "mode": "rule", "fallback": True}

    _INSIGHT_CACHE.update(signature=signature, at=now, value=result)
    return result
