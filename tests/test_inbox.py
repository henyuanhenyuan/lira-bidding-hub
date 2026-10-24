from app import config, db, inbox

CSV = """target_id,ts,collector,source_tier,list_price,coupons,promotions,coin_rate,coin_cap,account_tier,title
t1,2026-10-23T02:17:00+08:00,yd-v1,3,299,[],[],0,0,normal,竞品A
t1,2026-10-24T02:17:00+08:00,yd-v1,3,269,[],[],0,0,normal,竞品A
"""


def drop(name: str, content: str):
    inbox.inbox_dir()
    path = config.DATA_DIR / "inbox" / name
    path.write_text(content, encoding="utf-8")
    return path


def test_scan_ingests_and_moves_file():
    path = drop("day1.csv", CSV)
    results = inbox.scan_once()

    assert any(r.get("rows_ok") == 2 for r in results)
    assert not path.exists()

    with db.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM snapshot").fetchone()["c"] == 2
        row = conn.execute(
            "SELECT * FROM inbox_file WHERE name = 'day1.csv'"
        ).fetchone()
    assert row["status"] == "ingested"
    assert row["rows_ok"] == 2


def test_same_file_content_is_skipped_again():
    drop("day1.csv", CSV)
    inbox.scan_once()
    # 同名同内容再投，应判定为已处理
    drop("day1.csv", CSV)
    results = inbox.scan_once()
    assert any(r.get("skipped") for r in results)
    with db.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM snapshot").fetchone()["c"] == 2


def test_bad_file_goes_to_failed_and_records_error():
    drop("broken.csv", "target_id,ts\nonly,one-column\n")
    inbox.scan_once()
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM inbox_file WHERE name = 'broken.csv'"
        ).fetchone()
    assert row["status"] == "failed"
    assert row["error"]


def test_pending_count_reflects_inbox():
    drop("pending.csv", CSV)
    assert inbox.pending_count() >= 1
