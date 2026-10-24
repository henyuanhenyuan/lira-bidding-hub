from __future__ import annotations

import hashlib
import json
import re
import time

import httpx

from . import config, db, metrics, notify

# 领域词典：宁可覆盖窄一点，也不要制造噪音
TOPICS: dict[str, list[str]] = {
    "物流发货": ["发货", "物流", "快递", "到货", "配送", "迟迟", "慢", "延误"],
    "质量成分": ["质量", "成分", "用料", "正品", "假货", "变质", "过敏", "刺激"],
    "价格性价比": ["价格", "性价比", "贵", "便宜", "划算", "优惠", "涨价"],
    "包装": ["包装", "瓶子", "漏", "破损", "盒子", "压扁"],
    "客服售后": ["客服", "售后", "退货", "退款", "态度", "回复", "不给"],
    "使用效果": ["效果", "好用", "没用", "干枯", "毛躁", "顺滑", "控油", "起泡"],
    "味道气味": ["味道", "气味", "香", "刺鼻", "难闻"],
}

NEGATIVE_HINTS = ["差", "慢", "贵", "假", "漏", "难闻", "没用", "退货", "退款", "失望", "破损"]

SPIKE_DELTA = 0.15
SPIKE_MIN_COUNT = 3


def _hash(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def add_reviews(conn, target_id: str, reviews: list[dict]) -> dict:
    inserted = duplicates = skipped = 0
    for r in reviews:
        content = (r.get("content") or "").strip()
        if not content:
            skipped += 1
            continue
        try:
            conn.execute(
                "INSERT INTO review (id, target_id, ts, rating, content, content_hash,"
                " created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    db.new_id(), target_id, r.get("ts") or db.now_iso(),
                    r.get("rating"), content, _hash(content), db.now_iso(),
                ),
            )
            inserted += 1
        except Exception as exc:
            if not db.is_unique_violation(exc):
                raise
            duplicates += 1
    return {"inserted": inserted, "duplicates": duplicates, "skipped": skipped}


def classify(text: str) -> set[str]:
    hits = set()
    for name, words in TOPICS.items():
        if any(w in text for w in words):
            hits.add(name)
    return hits


def is_negative(rating: int | None, text: str) -> bool:
    if rating is not None:
        return rating <= 2
    return any(w in text for w in NEGATIVE_HINTS)


def _deterministic_summary(topics: list[dict], total: int) -> str:
    if not topics:
        return f"近窗口内 {total} 条评论，未识别出集中话题。"
    top = topics[0]
    return (
        f"近窗口 {total} 条评论，最集中的话题是「{top['name']}」"
        f"（{top['count']} 条，负面 {top['negative_share']:.0%}）。"
    )


SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "focus": {"type": "string"},
        "advice": {"type": "string"},
    },
    "required": ["focus", "advice"],
}

# 任务收窄到"选题 + 给建议"，数字一律由程序拼；实测这样 4B 才稳定
SUMMARY_PROMPT = """你是电商竞品分析师。输入是评论话题统计。
选出负面占比最高的一个话题，原样照抄它的话题名，再给一句不超过 30 字的建议。
只输出 JSON：{"focus":"话题名","advice":"建议"}。建议里不要出现数字。

示例输入：{"topics":[{"name":"物流发货","count":4,"negative_share":1.0}]}
示例输出：{"focus":"物流发货","advice":"主打发货速度与时效承诺"}
"""


def _llm_summary(stats: list[dict], total: int) -> str | None:
    """模型只负责选话题 + 给建议，数字由程序拼，避免编造。"""
    if config.LLM_ENABLED == "off" or not stats:
        return None
    for _ in range(2):  # 4B 模型偶发照抄占位符，重试一次
        text = _try_summary_once(stats, total)
        if text:
            return text
    return None


def _try_summary_once(stats: list[dict], total: int) -> str | None:
    started = time.perf_counter()
    text, prompt_tokens, completion_tokens = _summary_call(stats, total)
    metrics.record(
        "review_summary", model=config.OLLAMA_MODEL, ok=text is not None,
        fallback=text is None,
        latency_ms=int((time.perf_counter() - started) * 1000),
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
    )
    return text


def _summary_call(stats: list[dict], total: int) -> tuple[str | None, int, int]:
    if metrics.budget_exceeded():
        return None, 0, 0
    try:
        r = httpx.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "stream": False,
                "think": False,
                "format": SUMMARY_SCHEMA,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 120,
                    "repeat_penalty": 1.15,
                },
                "messages": [
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": json.dumps(
                        {"topics": [
                            {"name": t["name"], "count": t["count"],
                             "negative_share": t["negative_share"]}
                            for t in stats[:3]
                        ]},
                        ensure_ascii=False,
                    )},
                ],
            },
            timeout=config.LLM_TIMEOUT_S,
        )
        if r.status_code != 200:
            return None, 0, 0
        payload = r.json()
        prompt_tokens = int(payload.get("prompt_eval_count") or 0)
        completion_tokens = int(payload.get("eval_count") or 0)
        data = json.loads((payload.get("message", {}).get("content") or "").strip())
        focus = str(data.get("focus", "")).strip()
        advice = str(data.get("advice", "")).strip()

        names = {t["name"] for t in stats}
        if focus not in names or not advice:
            return None, prompt_tokens, completion_tokens
        if re.search(r"\d", advice):  # 建议里出现数字 → 无法核验，作废
            return None, prompt_tokens, completion_tokens

        topic = next(t for t in stats if t["name"] == focus)
        return (
            f"近窗口 {total} 条评论，最值得关注的是「{focus}」"
            f"（{topic['count']} 条，负面 {topic['negative_share']:.0%}）；{advice}",
            prompt_tokens,
            completion_tokens,
        )
    except Exception:
        return None, 0, 0


def analyze(conn, target_id: str, window_days: int = 7) -> dict | None:
    rows = conn.execute(
        "SELECT * FROM review WHERE target_id = ? AND datetime(ts) >= datetime('now', ?)"
        " ORDER BY ts DESC",
        (target_id, f"-{window_days} days"),
    ).fetchall()
    if not rows:
        return None

    total = len(rows)
    hits: dict[str, dict] = {}
    for r in rows:
        for name in classify(r["content"]):
            rec = hits.setdefault(name, {"count": 0, "negative": 0, "examples": []})
            rec["count"] += 1
            if is_negative(r["rating"], r["content"]):
                rec["negative"] += 1
            if len(rec["examples"]) < 2:
                rec["examples"].append(r["content"][:50])

    topics = [
        {
            "name": name,
            "count": rec["count"],
            "share": round(rec["count"] / total, 3),
            "negative_share": round(rec["negative"] / rec["count"], 3),
            "examples": rec["examples"],
        }
        for name, rec in hits.items()
    ]
    topics.sort(key=lambda t: (-t["count"], t["name"]))

    opportunities = [
        f"竞品在「{t['name']}」的负面占比 {t['negative_share']:.0%}"
        f"（{t['count']} 条），可作为我方主图/详情页的差异化卖点"
        for t in topics
        if t["count"] >= SPIKE_MIN_COUNT and t["negative_share"] >= 0.5
    ]

    summary = _llm_summary(topics, total)
    generated_by = "llm" if summary else "template:v1"
    if not summary:
        summary = _deterministic_summary(topics, total)

    insight_id = db.new_id()
    conn.execute(
        "INSERT INTO review_insight (id, target_id, window_days, generated_at,"
        " review_count, topics, opportunities, summary, generated_by)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (
            insight_id, target_id, window_days, db.now_iso(), total,
            json.dumps(topics, ensure_ascii=False),
            json.dumps(opportunities, ensure_ascii=False), summary, generated_by,
        ),
    )

    event_id = _maybe_emit_spike(conn, target_id, insight_id, topics)
    insight = get_insight(conn, insight_id)
    insight["event_id"] = event_id
    return insight


def _prev_insight(conn, target_id: str, current_id: str):
    return conn.execute(
        "SELECT * FROM review_insight WHERE target_id = ? AND id != ?"
        " ORDER BY generated_at DESC LIMIT 1",
        (target_id, current_id),
    ).fetchone()


def _maybe_emit_spike(conn, target_id: str, insight_id: str, topics: list[dict]) -> str | None:
    prev = _prev_insight(conn, target_id, insight_id)
    if not prev:
        return None
    prev_topics = {t["name"]: t for t in json.loads(prev["topics"])}

    spikes = []
    for t in topics:
        old = prev_topics.get(t["name"])
        if not old:
            continue
        delta = t["negative_share"] - old["negative_share"]
        if t["count"] >= SPIKE_MIN_COUNT and delta >= SPIKE_DELTA:
            spikes.append((t["name"], old["negative_share"], t["negative_share"], delta))
    if not spikes:
        return None

    name, before, after, delta = max(spikes, key=lambda s: s[3])
    note = f"竞品评论「{name}」负面占比由 {before:.0%} 升至 {after:.0%}"
    exists = conn.execute(
        "SELECT 1 FROM event WHERE target_id = ? AND type = 'review_spike'"
        " AND note = ? AND datetime(ts) >= datetime('now', '-1 day')",
        (target_id, note),
    ).fetchone()
    if exists:
        return None

    event_id = db.new_id()
    conn.execute(
        "INSERT INTO event (id, target_id, ts, type, severity, gate_level, suppressed,"
        " note, evidence, rule_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            event_id, target_id, db.now_iso(), "review_spike", "L2", "confirm", 0,
            note, json.dumps([f"insight:{insight_id}"], ensure_ascii=False), "review-v1",
        ),
    )
    notify.send(f"【竞品评论异动】{note}")
    return event_id


def get_insight(conn, insight_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM review_insight WHERE id = ?", (insight_id,)
    ).fetchone()
    if not row:
        return None
    return {
        **dict(row),
        "topics": json.loads(row["topics"]),
        "opportunities": json.loads(row["opportunities"]),
    }


def latest_insight(conn, target_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id FROM review_insight WHERE target_id = ?"
        " ORDER BY generated_at DESC LIMIT 1",
        (target_id,),
    ).fetchone()
    return get_insight(conn, row["id"]) if row else None


def list_reviews(conn, target_id: str, limit: int = 100) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT id, target_id, ts, rating, content FROM review"
            " WHERE target_id = ? ORDER BY ts DESC LIMIT ?",
            (target_id, limit),
        ).fetchall()
    ]


DEMO_REVIEWS = [
    {"rating": 2, "content": "发货太慢了，等了五天才到", "ts": None},
    {"rating": 2, "content": "物流一直不更新，客服也不回复", "ts": None},
    {"rating": 1, "content": "快递慢就算了，包装还破损了", "ts": None},
    {"rating": 5, "content": "味道很好闻，洗完很顺滑", "ts": None},
    {"rating": 4, "content": "控油效果不错，就是价格有点贵", "ts": None},
    {"rating": 3, "content": "使用效果一般，起泡不多", "ts": None},
    {"rating": 2, "content": "到货太慢了，急着用没赶上", "ts": None},
    {"rating": 5, "content": "性价比很高，会回购", "ts": None},
]


def seed(conn, target_id: str) -> dict:
    return add_reviews(conn, target_id, DEMO_REVIEWS)
