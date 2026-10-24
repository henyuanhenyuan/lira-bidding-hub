from app import db, ingest
from app.contracts import Coin, Coupon, Observation, SnapshotIn

D1 = "2026-10-23T02:17:00+08:00"
D2 = "2026-10-24T02:17:00+08:00"


def snap(price, ts, coupons=None, collector="yd-v1", tier=3, target="t1",
         title=None, image=None):
    return SnapshotIn(
        target_id=target, ts=ts, collector=collector, source_tier=tier,
        observation=Observation(
            list_price=price, coupons=coupons or [], promotions=[],
            coin=Coin(rate=0, cap=0), title=title or f"竞品-{target}",
            main_image_url=image,
        ),
    )


def test_title_change_emits_semantic_event():
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D1, title="竞品A 洗发水 500ml 赠小样")])
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D2, title="竞品A 洗发水 500ml 买一送一")])
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM event WHERE type = 'title_change'"
        ).fetchone()
    assert row is not None
    assert "买一送一" in row["note"]
    assert row["rule_version"] == "semantic-v1"


def test_image_change_emits_semantic_event():
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D1, image="http://img/1.jpg")])
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D2, image="http://img/2.jpg")])
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM event WHERE type = 'image_change'").fetchone()
    assert row is not None
    assert row["note"] == "主图已更换"


def test_first_snapshot_has_no_semantic_event():
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D1)])
    with db.get_db() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM event WHERE type IN ('title_change','image_change')"
        ).fetchone()["c"]
    assert n == 0


def test_ingest_creates_target_and_point():
    with db.get_db() as conn:
        r = ingest.ingest(conn, [snap(299, D1)])
    assert r.rows_ok == 1 and r.rows_rejected == 0
    with db.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM target").fetchone()["c"] == 1
        assert conn.execute("SELECT COUNT(*) c FROM price_point").fetchone()["c"] == 1


def test_duplicate_snapshot_is_skipped():
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D1)])
    with db.get_db() as conn:
        r = ingest.ingest(conn, [snap(299, D1)])
    assert r.rows_dup == 1
    assert r.rows_ok == 0


def test_price_drop_creates_event():
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D1)])
    with db.get_db() as conn:
        r = ingest.ingest(conn, [snap(239, D2)])
    assert r.events_created >= 1
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM event ORDER BY ts DESC LIMIT 1").fetchone()
    assert row["type"] == "price_drop"
    assert row["severity"] == "L2"  # 三级来源，L3 被降级；这里幅度 ~20% 仍是 L2


def test_missing_price_rejects_row():
    bad = SnapshotIn(
        target_id="t9", ts=D1, collector="x", source_tier=4,
        observation=Observation(list_price=None),
    )
    with db.get_db() as conn:
        r = ingest.ingest(conn, [bad])
    assert r.rows_rejected == 1
    assert r.errors


def test_source_switch_marked_suppressed():
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D1, collector="yd-v1")])
    with db.get_db() as conn:
        ingest.ingest(conn, [snap(299, D2, collector="api-vendor")])
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM event ORDER BY ts DESC LIMIT 1").fetchone()
    assert row["type"] == "source_switch"
    assert row["suppressed"] == 1
