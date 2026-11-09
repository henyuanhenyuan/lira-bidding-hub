from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import db, embeddings, vectorstore

RRF_K = 60


@dataclass
class Case:
    id: str
    category: str
    event_type: str
    price_band: str
    delta_pct: float | None
    summary: str
    attribution: str
    decision: str | None
    outcome_7d: str | None
    ts: str
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "category": self.category, "event_type": self.event_type,
            "price_band": self.price_band, "delta_pct": self.delta_pct,
            "summary": self.summary, "attribution": self.attribution,
            "decision": self.decision, "outcome_7d": self.outcome_7d,
            "ts": self.ts, "score": round(self.score, 4),
        }


def collection_name(provider: str, dim: int) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in provider)
    return f"case_embeddings_{safe}_{dim}"


def price_band_of(price: float) -> str:
    lo = int(price // 50) * 50
    return f"{lo}-{lo + 50}"


def _band_index(band: str) -> int:
    try:
        return int(band.split("-")[0]) // 50
    except (ValueError, IndexError):
        return -1


def create(
    conn,
    *,
    category: str,
    event_type: str,
    summary: str,
    attribution: str,
    price_band: str,
    delta_pct: float | None = None,
    decision: str | None = None,
    outcome_7d: str | None = None,
    ts: str | None = None,
    case_id: str | None = None,
) -> str:
    text = f"{summary}\n{attribution}\n{category} {event_type}"
    vec, provider = embeddings.embed(text)
    cid = case_id or db.new_id()
    ts_value = ts or db.now_iso()
    conn.execute(
        "INSERT INTO \"case\" (id, category, event_type, price_band, delta_pct,"
        " summary, attribution, decision, outcome_7d, ts, embed_provider, dim)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT (id) DO UPDATE SET category=excluded.category,"
        " event_type=excluded.event_type, price_band=excluded.price_band,"
        " delta_pct=excluded.delta_pct, summary=excluded.summary,"
        " attribution=excluded.attribution, decision=excluded.decision,"
        " outcome_7d=excluded.outcome_7d, ts=excluded.ts,"
        " embed_provider=excluded.embed_provider, dim=excluded.dim",
        (
            cid, category, event_type, price_band, delta_pct, summary, attribution,
            decision, outcome_7d, ts_value, provider, len(vec),
        ),
    )
    payload: dict[str, Any] = {
        "category": category,
        "event_type": event_type,
        "price_band": price_band,
        "ts": ts_value,
    }
    if delta_pct is not None:
        payload["delta_pct"] = float(delta_pct)
    vectorstore.PgVectorStore().upsert(
        collection_name(provider, len(vec)),
        [vectorstore.Point(cid, vec, payload)],
    )
    return cid


def _row_to_case(row, score: float = 0.0) -> Case:
    return Case(
        id=row["id"], category=row["category"], event_type=row["event_type"],
        price_band=row["price_band"], delta_pct=row["delta_pct"],
        summary=row["summary"], attribution=row["attribution"],
        decision=row["decision"], outcome_7d=row["outcome_7d"], ts=row["ts"],
        score=score,
    )


def search(
    conn,
    *,
    query: str,
    category: str | None,
    event_type: str | None,
    price_band: str | None,
    delta_pct: float | None = None,
    limit: int = 3,
) -> list[Case]:
    """四级：结构化预过滤 → 向量召回 → 关键词召回 → RRF 融合。"""
    where = ["1=1"]
    params: list[Any] = []
    if category:
        where.append("category = ?")
        params.append(category)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)

    rows = conn.execute(
        f"SELECT * FROM {_TABLE} WHERE {' AND '.join(where)} LIMIT 500", params
    ).fetchall()
    if not rows:
        rows = conn.execute(f"SELECT * FROM {_TABLE} LIMIT 500").fetchall()
    if not rows:
        return []

    qvec, provider = embeddings.embed(query)
    by_id = {r["id"]: r for r in rows}

    # 向量召回：集合按 provider + 维度隔离，结构化条件下推为 payload 过滤
    store = vectorstore.PgVectorStore()
    filters = {
        key: value
        for key, value in (("category", category), ("event_type", event_type))
        if value
    }
    hits = store.search(
        collection_name(provider, len(qvec)), qvec, top_k=20,
        filters=filters or None,
    )
    if not hits and filters:
        hits = store.search(collection_name(provider, len(qvec)), qvec, top_k=20)
    vector_rank = [hit.id for hit in hits if hit.id in by_id]

    # 关键词召回
    keyword_rank: list[str] = []
    try:
        escaped = (
            (query or "")[:60]
            .replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        needle = f"%{escaped}%"
        fts_rows = conn.execute(
            'SELECT id FROM "case" WHERE summary ILIKE ? ESCAPE \'\\\''
            " OR attribution ILIKE ? ESCAPE '\\' LIMIT 20",
            (needle, needle),
        ).fetchall()
        keyword_rank = [r["id"] for r in fts_rows if r["id"] in by_id]
    except Exception:
        keyword_rank = []

    # RRF 融合
    fused: dict[str, float] = {}
    for rank, cid in enumerate(vector_rank):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, cid in enumerate(keyword_rank):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    if not fused:  # 两路都空时退化为预过滤顺序
        fused = {r["id"]: 0.0 for r in rows[:20]}

    # 重排：价格带接近 + 幅度接近 加一点分
    def bonus(cid: str) -> float:
        r = by_id[cid]
        b = 0.0
        if price_band and r["price_band"] == price_band:
            b += 0.010
        if delta_pct is not None and r["delta_pct"] is not None:
            b += max(0.0, 0.006 - abs(abs(r["delta_pct"]) - abs(delta_pct)) * 0.03)
        return b

    # 先粗排取较多候选，再用轻量重排器精排
    coarse = sorted(
        fused.items(), key=lambda kv: -(kv[1] + bonus(kv[0]))
    )[: max(limit * 3, 9)]

    candidates = []
    for cid, fused_score in coarse:
        row = by_id[cid]
        candidates.append({
            "id": cid,
            "summary": row["summary"],
            "attribution": row["attribution"],
            "price_band": row["price_band"],
            "delta_pct": row["delta_pct"],
            "ts": row["ts"],
            "_fused": fused_score,
        })

    from . import rerank as reranker  # 延迟导入，避免循环依赖

    final = reranker.rerank(
        candidates, query=query, price_band=price_band,
        delta_pct=delta_pct, limit=limit,
    )
    return [_row_to_case(by_id[c["id"]], c["_fused"]) for c in final]


_TABLE = '"case"'


def _fts_query(text: str) -> str:
    """trigram 分词下，用原文片段做短语匹配。"""
    cleaned = (text or "").replace('"', " ").strip()
    if not cleaned:
        return '""'
    return f'"{cleaned[:60]}"'


SEED_CASES = [
    dict(
        category="洗护", event_type="price_drop", price_band="250-300", delta_pct=-0.10,
        summary="竞品在大促前 48 小时把套装降到 269 元，并同步上了店铺券。",
        attribution="大促前的价格试探，通常用于抢占搜索位；历史 3 次中 2 次在 72 小时内回调。",
        decision="hold", outcome_7d="未跟价，7 日后竞品回调至 299，我方销量未受影响。",
    ),
    dict(
        category="洗护", event_type="price_drop", price_band="100-150", delta_pct=-0.25,
        summary="竞品洗发水从 199 直降 149，无券，持续 5 天以上。",
        attribution="清库存或新品换代，价格未回调，属于结构性降价。",
        decision="adjust_coupon", outcome_7d="以券对冲后价差收窄到 8%，7 日销量持平。",
    ),
    dict(
        category="洗护", event_type="band_breach", price_band="50-100", delta_pct=0.0,
        summary="竞品护发素长期维持 89 元，击穿我方 100 元价格带。",
        attribution="对方以低价款引流，非短期促销，正面跟价会损伤主款毛利。",
        decision="hold", outcome_7d="维持价格，靠赠品提升转化，7 日转化率提升 1.2pt。",
    ),
    dict(
        category="美妆", event_type="price_drop", price_band="300-350", delta_pct=-0.15,
        summary="精华液降价 15% 并叠加跨店满减，配合直播引流。",
        attribution="直播专享价，活动结束后恢复，属于渠道价而非公开价。",
        decision="hold", outcome_7d="活动 3 天后恢复原价，短期波动不影响搜索排名。",
    ),
    dict(
        category="美妆", event_type="price_rise", price_band="200-250", delta_pct=0.12,
        summary="面膜提价 12%，同时更换主图强调成分升级。",
        attribution="换代升级后的价格上调，通常稳定，不会短期回落。",
        decision="follow", outcome_7d="我方跟进提价 6%，销量下降 3%，毛利提升 9%。",
    ),
]


def seed(conn) -> int:
    n = 0
    for c in SEED_CASES:
        exists = conn.execute(
            'SELECT 1 FROM "case" WHERE summary = ?', (c["summary"],)
        ).fetchone()
        if exists:
            continue
        create(conn, **c)
        n += 1
    return n


def count(conn) -> int:
    return conn.execute('SELECT COUNT(*) c FROM "case"').fetchone()["c"]
