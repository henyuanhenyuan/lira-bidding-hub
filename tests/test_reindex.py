from app import cases, db, reindex


def test_reindex_rebuilds_case_vectors():
    with db.get_db() as conn:
        conn.execute(
            'INSERT INTO "case" (id, category, event_type, price_band, delta_pct,'
            " summary, attribution, decision, outcome_7d, ts, embed_provider, dim)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-1", "洗护", "price_drop", "250-300", -0.10,
                "竞品大促前降价 10%", "大促价格试探，72 小时内多半回调",
                "hold", None, "2026-10-24T00:00:00+00:00", "hash:256", 256,
            ),
        )

    with db.get_db() as conn:
        counts = reindex.reindex(conn)

    assert counts["cases"] == 1
    with db.get_db() as conn:
        found = cases.search(
            conn, query="竞品大促前降价", category=None,
            event_type="price_drop", price_band="250-300",
            delta_pct=-0.10, limit=3,
        )
    assert found
    assert found[0].id == "legacy-1"
