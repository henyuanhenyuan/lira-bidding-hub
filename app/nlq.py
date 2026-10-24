from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import db

MAX_ROWS = 50


@dataclass
class Template:
    id: str
    title: str
    description: str
    keywords: list[str]
    params: dict[str, dict]
    sql: Callable[[dict], tuple[str, list]]
    render: Callable[[list[dict], dict], str]
    examples: list[str] = field(default_factory=list)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# ---------------- 模板实现 ----------------

def _price_drops(p: dict):
    return (
        "SELECT t.title, e.ts, e.severity, e.note FROM event e"
        " JOIN target t ON t.id = e.target_id"
        " WHERE e.type = 'price_drop' AND e.suppressed = 0"
        " AND datetime(e.ts) >= datetime('now', ?)"
        " ORDER BY e.ts DESC LIMIT ?",
        [f"-{p['days']} days", MAX_ROWS],
    )


def _render_drops(rows, p):
    if not rows:
        return f"最近 {p['days']} 天没有降价事件。"
    return f"最近 {p['days']} 天共 {len(rows)} 条降价事件，最近一条：{rows[0]['title']}｜{rows[0]['note']}"


def _events_by_severity(p: dict):
    return (
        "SELECT t.title, e.ts, e.type, e.severity, e.note FROM event e"
        " JOIN target t ON t.id = e.target_id"
        " WHERE e.severity = ? AND e.suppressed = 0"
        " AND datetime(e.ts) >= datetime('now', ?)"
        " ORDER BY e.ts DESC LIMIT ?",
        [p["severity"], f"-{p['days']} days", MAX_ROWS],
    )


def _render_severity(rows, p):
    if not rows:
        return f"最近 {p['days']} 天没有 {p['severity']} 级事件。"
    return f"最近 {p['days']} 天共有 {len(rows)} 条 {p['severity']} 级事件，涉及 {rows[0]['title']} 等。"


def _band_breaches(p: dict):
    return (
        "SELECT t.title, e.ts, e.note FROM event e"
        " JOIN target t ON t.id = e.target_id"
        " WHERE e.type = 'band_breach' AND e.suppressed = 0"
        " AND datetime(e.ts) >= datetime('now', ?)"
        " ORDER BY e.ts DESC LIMIT ?",
        [f"-{p['days']} days", MAX_ROWS],
    )


def _render_breach(rows, p):
    if not rows:
        return f"最近 {p['days']} 天没有价格带击穿。"
    names = "、".join(sorted({r["title"] for r in rows}))
    return f"最近 {p['days']} 天有 {len(rows)} 次价格带击穿，涉及：{names}。"


def _pending_suggestions(p: dict):
    return (
        "SELECT t.title, s.action, s.guardrail, s.narrative, s.created_at"
        " FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " WHERE s.status = 'pending' ORDER BY s.created_at DESC LIMIT ?",
        [MAX_ROWS],
    )


def _render_pending(rows, p):
    if not rows:
        return "当前没有待提交的建议。"
    return f"当前有 {len(rows)} 条待提交建议，最早一条针对 {rows[-1]['title']}。"


def _blocked(p: dict):
    return (
        "SELECT t.title, s.action, s.target_price, s.guardrail_note, s.created_at"
        " FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " WHERE s.guardrail = 'blocked' ORDER BY s.created_at DESC LIMIT ?",
        [MAX_ROWS],
    )


def _render_blocked(rows, p):
    if not rows:
        return "没有被毛利护栏拦截的建议。"
    return f"有 {len(rows)} 条建议被毛利率下限拦截，例如：{rows[0]['title']}｜{rows[0]['guardrail_note']}"


def _executed(p: dict):
    return (
        "SELECT t.title, s.action, s.executed_price, s.created_at"
        " FROM suggestion s"
        " LEFT JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " WHERE s.status = 'executed' AND datetime(s.created_at) >= datetime('now', ?)"
        " ORDER BY s.created_at DESC LIMIT ?",
        [f"-{p['days']} days", MAX_ROWS],
    )


def _render_executed(rows, p):
    if not rows:
        return f"最近 {p['days']} 天没有已执行的建议。"
    return f"最近 {p['days']} 天执行了 {len(rows)} 条建议。"


def _outcome_summary(p: dict):
    return (
        "SELECT o.result, COUNT(*) AS n FROM outcome o"
        " WHERE datetime(o.recorded_at) >= datetime('now', ?) GROUP BY o.result",
        [f"-{p['days']} days"],
    )


def _render_outcome(rows, p):
    if not rows:
        return f"最近 {p['days']} 天没有回收执行结果。"
    text = "、".join(f"{r['result']} {r['n']} 条" for r in rows)
    return f"最近 {p['days']} 天的结果回收：{text}。"


def _price_trend(p: dict):
    return (
        "SELECT t.title, pp.ts, pp.price_low, pp.price_high, pp.confidence"
        " FROM price_point pp JOIN target t ON t.id = pp.target_id"
        " WHERE t.title LIKE ? AND datetime(pp.ts) >= datetime('now', ?)"
        " ORDER BY pp.ts ASC LIMIT ?",
        [f"%{p['target']}%", f"-{p['days']} days", MAX_ROWS],
    )


def _render_trend(rows, p):
    if not rows:
        return f"最近 {p['days']} 天没有「{p['target']}」的价格数据。"
    first, last = rows[0], rows[-1]
    change = (last["price_low"] - first["price_low"]) / first["price_low"] if first["price_low"] else 0
    return (
        f"「{last['title']}」最近 {p['days']} 天有 {len(rows)} 个价格点，"
        f"到手价从 {first['price_low']:.2f} 变为 {last['price_low']:.2f}（{change:+.1%}）。"
    )


def _overview(p: dict):
    return (
        "SELECT t.title, t.my_price, t.mapping_status,"
        " (SELECT pp.price_low FROM price_point pp WHERE pp.target_id = t.id"
        "  ORDER BY pp.ts DESC LIMIT 1) AS latest_price,"
        " (SELECT COUNT(*) FROM event e WHERE e.target_id = t.id AND e.suppressed = 0) AS event_count"
        " FROM target t WHERE t.active = 1 ORDER BY t.title LIMIT ?",
        [MAX_ROWS],
    )


def _render_overview(rows, p):
    if not rows:
        return "还没有监控任何竞品。"
    return f"当前监控 {len(rows)} 个竞品，事件最多的是 {max(rows, key=lambda r: r['event_count'])['title']}。"


def _negative_topics(p: dict):
    return (
        "SELECT t.title, ri.topics, ri.generated_at FROM review_insight ri"
        " JOIN target t ON t.id = ri.target_id"
        " WHERE ri.id = (SELECT id FROM review_insight r2 WHERE r2.target_id = ri.target_id"
        "  ORDER BY generated_at DESC LIMIT 1)"
        " AND datetime(ri.generated_at) >= datetime('now', ?)"
        " ORDER BY ri.generated_at DESC LIMIT ?",
        [f"-{p['days']} days", MAX_ROWS],
    )


def _render_topics(rows, p):
    if not rows:
        return f"最近 {p['days']} 天还没有评论洞察。"
    pairs = []
    for r in rows:
        for t in db.loads(r["topics"], []):
            if t.get("negative_share", 0) >= 0.5 and t.get("count", 0) >= 3:
                pairs.append((t["negative_share"], r["title"], t["name"]))
    if not pairs:
        return "近期评论里没有负面集中的话题。"
    pairs.sort(reverse=True)
    top = pairs[0]
    return f"负面最集中的是 {top[1]} 的「{top[2]}」（负面占比 {top[0]:.0%}）。"


TEMPLATES: dict[str, Template] = {}


def _register(t: Template) -> None:
    TEMPLATES[t.id] = t


_register(Template(
    id="price_drops",
    title="最近降价",
    description="列出最近 N 天的降价事件",
    keywords=["降价", "下跌", "下调", "便宜了", "降价事件"],
    params={"days": {"type": "int", "default": 7, "min": 1, "max": 90}},
    sql=_price_drops,
    render=_render_drops,
    examples=["最近 7 天有哪些降价？", "最近 30 天降价情况"],
))

_register(Template(
    id="events_by_severity",
    title="按级别查事件",
    description="按 L1/L2/L3 级别查询事件",
    keywords=["紧急", "L3", "L2", "L1", "重要事件", "告警"],
    params={
        "severity": {"type": "enum", "default": "L3", "values": ["L1", "L2", "L3"]},
        "days": {"type": "int", "default": 7, "min": 1, "max": 90},
    },
    sql=_events_by_severity,
    render=_render_severity,
    examples=["最近的 L3 事件", "最近 30 天的紧急告警"],
))

_register(Template(
    id="band_breach",
    title="价格带击穿",
    description="竞品到手价击穿我方价格带",
    keywords=["击穿", "价格带", "低于我们", "破价"],
    params={"days": {"type": "int", "default": 14, "min": 1, "max": 90}},
    sql=_band_breaches,
    render=_render_breach,
    examples=["最近有没有价格带被击穿？"],
))

_register(Template(
    id="pending_suggestions",
    title="待提交建议",
    description="还没提交执行的建议",
    keywords=["待提交", "待处理", "未提交", "建议"],
    params={},
    sql=_pending_suggestions,
    render=_render_pending,
    examples=["现在有哪些待提交的建议？"],
))

_register(Template(
    id="guardrail_blocked",
    title="被护栏拦截",
    description="因毛利率低于下限被拦截的建议",
    keywords=["拦截", "护栏", "毛利", "被拦下"],
    params={},
    sql=_blocked,
    render=_render_blocked,
    examples=["有哪些建议被毛利护栏拦截了？"],
))

_register(Template(
    id="executed",
    title="已执行建议",
    description="最近已执行的建议",
    keywords=["已执行", "执行了", "落地"],
    params={"days": {"type": "int", "default": 30, "min": 1, "max": 180}},
    sql=_executed,
    render=_render_executed,
    examples=["最近 30 天执行了哪些建议？"],
))

_register(Template(
    id="outcome_summary",
    title="结果回收",
    description="执行后 7 日结果的分布",
    keywords=["结果", "效果", "回收", "有没有用", "改善"],
    params={"days": {"type": "int", "default": 30, "min": 1, "max": 180}},
    sql=_outcome_summary,
    render=_render_outcome,
    examples=["最近的结果回收怎么样？"],
))

_register(Template(
    id="price_trend",
    title="竞品价格走势",
    description="指定竞品最近的价格变化",
    keywords=["走势", "价格变化", "价格趋势"],
    params={
        "target": {"type": "text", "default": ""},
        "days": {"type": "int", "default": 14, "min": 1, "max": 90},
    },
    sql=_price_trend,
    render=_render_trend,
    examples=["竞品A最近的价格走势"],
))

_register(Template(
    id="overview",
    title="监控概览",
    description="当前监控的竞品与各自事件数",
    keywords=["概览", "总览", "有哪些竞品", "监控了什么"],
    params={},
    sql=_overview,
    render=_render_overview,
    examples=["现在监控了哪些竞品？"],
))

_register(Template(
    id="negative_topics",
    title="负面话题",
    description="评论里负面最集中的话题",
    keywords=["评论", "差评", "负面", "口碑"],
    params={"days": {"type": "int", "default": 14, "min": 1, "max": 180}},
    sql=_negative_topics,
    render=_render_topics,
    examples=["竞品评论里最大的问题是什么？"],
))


# ---------------- 路由与参数抽取 ----------------

def _extract_days(question: str, default: int) -> int:
    m = re.search(r"(\d+)\s*天", question)
    if m:
        return _clamp(int(m.group(1)), 1, 180)
    m = re.search(r"近\s*(\d+)\s*日", question)
    if m:
        return _clamp(int(m.group(1)), 1, 180)
    if "今天" in question or "当日" in question:
        return 1
    if "一周" in question or "本周" in question:
        return 7
    if "一个月" in question or "本月" in question or "30天" in question:
        return 30
    return default


def _extract_severity(question: str) -> str:
    if "L3" in question or "紧急" in question:
        return "L3"
    if "L2" in question or "关注" in question:
        return "L2"
    if "L1" in question or "信息" in question:
        return "L1"
    return "L3"


def _extract_target(question: str, targets: list[str]) -> str:
    for title in targets:
        if title and title in question:
            return title
        # 允许只写简称，比如“竞品A”
        short = title.split("·")[0].split(" ")[0]
        if short and len(short) >= 2 and short in question:
            return short
    return ""


def _match_template(question: str) -> Template | None:
    best, best_hits = None, 0
    for t in TEMPLATES.values():
        hits = sum(1 for k in t.keywords if k.lower() in question.lower())
        if hits > best_hits:
            best, best_hits = t, hits
    return best


def _build_params(t: Template, question: str, targets: list[str]) -> dict:
    params: dict[str, Any] = {}
    for name, spec in t.params.items():
        if name == "days":
            params[name] = _extract_days(question, spec.get("default", 7))
        elif name == "severity":
            params[name] = _extract_severity(question)
        elif name == "target":
            params[name] = _extract_target(question, targets)
        else:
            params[name] = spec.get("default")
    return params


def _validate(t: Template, params: dict) -> dict:
    """参数只允许落在模板声明的范围/枚举内。"""
    out: dict[str, Any] = {}
    for name, spec in t.params.items():
        v = params.get(name)
        kind = spec.get("type")
        if kind == "int":
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = spec["default"]
            out[name] = _clamp(v, spec.get("min", 0), spec.get("max", 10_000))
        elif kind == "enum":
            out[name] = v if v in spec["values"] else spec["default"]
        else:
            out[name] = str(v or "")[:40]
    return out


def templates_info() -> list[dict]:
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "params": t.params,
            "examples": t.examples,
        }
        for t in TEMPLATES.values()
    ]


def ask(conn, question: str) -> dict:
    """自然语言 → 模板 + 参数 → 预置 SQL。永不拼接用户输入到 SQL 文本。"""
    q = (question or "").strip()
    targets = [
        r["title"] for r in conn.execute(
            "SELECT title FROM target WHERE active = 1"
        ).fetchall()
    ]

    t = _match_template(q)
    if t is None:
        return {
            "ok": False,
            "reason": "no_template",
            "answer": "没听懂这个问题。可以试试下面这些问法：",
            "suggestions": [e for tpl in TEMPLATES.values() for e in tpl.examples][:6],
            "rows": [],
        }

    params = _validate(t, _build_params(t, q, targets))

    if t.id == "price_trend" and not params.get("target"):
        return {
            "ok": False,
            "reason": "missing_param",
            "template": t.id,
            "answer": f"要查「{t.title}」请带上竞品名称，例如：竞品A 最近的价格走势。",
            "rows": [],
        }

    sql, args = t.sql(params)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    rows = rows[:MAX_ROWS]

    return {
        "ok": True,
        "template": t.id,
        "template_title": t.title,
        "params": params,
        "answer": t.render(rows, params),
        "rows": rows,
        "matched_by": "rule",
    }
