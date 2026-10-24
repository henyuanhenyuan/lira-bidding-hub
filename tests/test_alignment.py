from app import alignment, db


def setup_target(target_id="t1", title="竞品A·洗护套装", price=None):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, external_id, title, my_sku, my_price, active)"
            " VALUES (?,?,?,?,NULL,NULL,1)",
            (target_id, "taobao", target_id, title),
        )
        conn.execute(
            "INSERT INTO my_product (sku, title, price, category, active)"
            " VALUES ('SKU-A','洗护套装 洗发水+护发素',289,'洗护',1)"
        )
        if price:
            conn.execute(
                "INSERT INTO price_point (target_id, ts, price_low, price_high,"
                " confidence, missing_fields, discontinuity) VALUES (?,?,?,?,?,?,0)",
                (target_id, "2026-10-24T02:17:00+08:00", price, price, 0.8, "[]"),
            )


def test_auto_suggest_creates_pending_candidates():
    setup_target(price=299)
    with db.get_db() as conn:
        created = alignment.auto_suggest(conn)
        rows = alignment.list_mappings(conn, "pending")
    assert created >= 1
    assert rows and rows[0]["my_sku"] == "SKU-A"
    assert rows[0]["score"] > 0


def test_confirm_updates_target_price_and_sku():
    setup_target(price=299)
    with db.get_db() as conn:
        alignment.auto_suggest(conn)
        m = conn.execute("SELECT * FROM mapping WHERE status='pending'").fetchone()
        result = alignment.decide(conn, m["id"], "confirmed", "qa")
    assert result["status"] == "confirmed"

    with db.get_db() as conn:
        t = conn.execute("SELECT * FROM target WHERE id='t1'").fetchone()
    assert t["my_sku"] == "SKU-A"
    assert t["my_price"] == 289
    assert t["mapping_status"] == "mapped"


def test_confirm_rejects_other_candidates():
    setup_target(price=299)
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO my_product (sku, title, price, category, active)"
            " VALUES ('SKU-B','洗护套装礼盒',299,'洗护',1)"
        )
        alignment.auto_suggest(conn)
        rows = conn.execute("SELECT * FROM mapping WHERE status='pending'").fetchall()
        assert len(rows) >= 2
        alignment.decide(conn, rows[0]["id"], "confirmed", "qa")
        still_pending = conn.execute(
            "SELECT COUNT(*) c FROM mapping WHERE status='pending'"
        ).fetchone()["c"]
    assert still_pending == 0


def test_auto_suggest_skips_already_mapped_targets():
    setup_target(price=299)
    with db.get_db() as conn:
        alignment.auto_suggest(conn)
        m = conn.execute("SELECT * FROM mapping WHERE status='pending'").fetchone()
        alignment.decide(conn, m["id"], "confirmed", "qa")
        again = alignment.auto_suggest(conn)
    assert again == 0


def test_decide_rejects_invalid_decision():
    setup_target(price=299)
    with db.get_db() as conn:
        alignment.auto_suggest(conn)
        m = conn.execute("SELECT * FROM mapping").fetchone()
        try:
            alignment.decide(conn, m["id"], "maybe", "qa")
        except ValueError:
            pass
        else:
            raise AssertionError("should reject invalid decision")
