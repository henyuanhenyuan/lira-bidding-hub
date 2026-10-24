import sqlite3

import pytest

from app import db, migrate


def test_postgres_dialect_translation(monkeypatch):
    monkeypatch.setattr(db, "BACKEND", "postgres")
    sql = (
        "SELECT * FROM t WHERE datetime(ts) >= datetime('now', ?)"
        " AND name = 'a%b' LIMIT ?"
    )
    out = db.to_backend_sql(sql)
    assert "(ts)::timestamptz" in out
    assert "(now() + (%s)::interval)" in out
    assert "a%%b" in out
    assert out.count("%s") == 2


def test_string_without_bind_keeps_percent(monkeypatch):
    monkeypatch.setattr(db, "BACKEND", "postgres")
    out = db.to_backend_sql("SELECT 'a%b'", bind=False)
    assert out == "SELECT 'a%b'"


@pytest.mark.skipif(
    db.BACKEND != "postgres", reason="migration target is PostgreSQL"
)
def test_migrate_copies_rows(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE target (id TEXT PRIMARY KEY, platform TEXT, external_id TEXT,"
        " title TEXT, my_sku TEXT, my_price REAL, active INTEGER)"
    )
    conn.execute(
        "INSERT INTO target VALUES ('t1','taobao','t1','竞品A',NULL,NULL,1)"
    )
    conn.execute(
        "CREATE TABLE snapshot (id TEXT PRIMARY KEY, target_id TEXT, ts TEXT,"
        " collector TEXT, source_tier INTEGER, payload TEXT, content_hash TEXT,"
        " backfill INTEGER, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO snapshot VALUES ('s1','t1','2026-10-24T02:17:00+08:00',"
        "'yd-v1',3,'{}','hash',0,'2026-10-24T02:17:00+00:00')"
    )
    conn.commit()
    conn.close()

    report = migrate.migrate(path, truncate=True)

    assert report["target"] == {"source": 1, "target": 1}
    assert report["snapshot"] == {"source": 1, "target": 1}
    assert report["event"].get("missing") is True

    with db.get_db() as c:
        row = c.execute("SELECT title FROM target WHERE id = ?", ("t1",)).fetchone()
    assert row["title"] == "竞品A"
