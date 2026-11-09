from __future__ import annotations

import math

from . import db, embeddings

# 相似度低于此值不生成候选，避免制造噪音
MIN_SCORE = 0.40
MAX_CANDIDATES = 3


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if norm == 0 else dot / norm


def _price_closeness(my_price: float | None, target_price: float | None) -> float:
    if not my_price or not target_price:
        return 0.5
    hi = max(my_price, target_price)
    return max(0.0, 1.0 - abs(my_price - target_price) / hi)


def _latest_price(conn, target_id: str) -> float | None:
    row = conn.execute(
        "SELECT price_low, price_high FROM price_point WHERE target_id = ?"
        " ORDER BY ts DESC LIMIT 1",
        (target_id,),
    ).fetchone()
    if not row:
        return None
    return (row["price_low"] + row["price_high"]) / 2


def upsert_mapping(conn, my_sku: str, target_id: str, score: float, method: str) -> str:
    row = conn.execute(
        "SELECT id, status FROM mapping WHERE my_sku = ? AND target_id = ?",
        (my_sku, target_id),
    ).fetchone()
    if row:
        if row["status"] == "pending":
            conn.execute(
                "UPDATE mapping SET score = ?, method = ? WHERE id = ?",
                (score, method, row["id"]),
            )
        return row["id"]
    mid = db.new_id()
    conn.execute(
        "INSERT INTO mapping (id, my_sku, target_id, score, method, status, created_at)"
        " VALUES (?,?,?,?,?,'pending',?)",
        (mid, my_sku, target_id, score, method, db.now_iso()),
    )
    return mid


def auto_suggest(conn) -> int:
    products = conn.execute(
        "SELECT * FROM my_product WHERE active = 1"
    ).fetchall()
    if not products:
        return 0

    pvecs = {p["sku"]: embeddings.embed(p["title"])[0] for p in products}

    targets = conn.execute(
        "SELECT * FROM target WHERE active = 1 AND mapping_status != 'mapped'"
    ).fetchall()

    created = 0
    for t in targets:
        has_confirmed = conn.execute(
            "SELECT 1 FROM mapping WHERE target_id = ? AND status = 'confirmed'",
            (t["id"],),
        ).fetchone()
        if has_confirmed:
            continue

        tvec = embeddings.embed(t["title"])[0]
        tprice = _latest_price(conn, t["id"])

        scored = []
        for p in products:
            s = 0.75 * _cos(pvecs[p["sku"]], tvec) + 0.25 * _price_closeness(
                p["price"], tprice
            )
            scored.append((s, p["sku"]))
        scored.sort(reverse=True)

        for score, sku in scored[:MAX_CANDIDATES]:
            if score < MIN_SCORE:
                continue
            upsert_mapping(conn, sku, t["id"], round(score, 4), "embedding")
            created += 1
    return created


def decide(conn, mapping_id: str, decision: str, actor: str) -> dict:
    if decision not in ("confirmed", "rejected"):
        raise ValueError("decision must be confirmed|rejected")
    row = conn.execute("SELECT * FROM mapping WHERE id = ?", (mapping_id,)).fetchone()
    if not row:
        raise KeyError(mapping_id)

    conn.execute(
        "UPDATE mapping SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
        (decision, db.now_iso(), actor, mapping_id),
    )

    if decision == "confirmed":
        product = conn.execute(
            "SELECT * FROM my_product WHERE sku = ?", (row["my_sku"],)
        ).fetchone()
        conn.execute(
            "UPDATE target SET my_sku = ?, my_price = ?, mapping_status = 'mapped'"
            " WHERE id = ?",
            (row["my_sku"], product["price"] if product else None, row["target_id"]),
        )
        # 同一竞品只保留一个确认关系
        conn.execute(
            "UPDATE mapping SET status = 'rejected', decided_at = ?, decided_by = ?"
            " WHERE target_id = ? AND id != ? AND status = 'pending'",
            (db.now_iso(), actor, row["target_id"], mapping_id),
        )

    return {"id": mapping_id, "status": decision, "my_sku": row["my_sku"],
            "target_id": row["target_id"]}


def list_mappings(conn, status: str | None = None) -> list[dict]:
    sql = (
        "SELECT m.*, t.title AS target_title, p.title AS my_title, p.price AS my_price"
        " FROM mapping m"
        " LEFT JOIN target t ON t.id = m.target_id"
        " LEFT JOIN my_product p ON p.sku = m.my_sku"
    )
    params: list = []
    if status:
        sql += " WHERE m.status = ?"
        params.append(status)
    sql += " ORDER BY m.score DESC, m.created_at DESC LIMIT 200"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
