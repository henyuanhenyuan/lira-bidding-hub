from __future__ import annotations

import sqlite3
from pathlib import Path

from . import db

TABLES = [
    "target",
    "snapshot",
    "price_point",
    "event",
    "suggestion",
    "action_log",
    "case",
    "ingest_log",
    "my_product",
    "mapping",
    "outcome",
    "inbox_file",
    "job_run",
    "review",
    "review_insight",
    "model_call",
    "approval_log",
    "app_user",
]


def migrate(
    sqlite_path: str | Path, *, truncate: bool = False
) -> dict[str, dict[str, int | bool]]:
    """把 SQLite 数据搬到 PostgreSQL。目标库由 LIRA_DATABASE_URL 指定。"""
    if db.BACKEND != "postgres":
        raise RuntimeError("目标必须是 PostgreSQL：请设置 LIRA_DATABASE_URL")

    src = sqlite3.connect(str(sqlite_path))
    src.row_factory = sqlite3.Row
    db.init_db()
    report: dict[str, dict[str, int | bool]] = {}

    try:
        with db.get_db() as dst:
            if truncate:
                joined = ", ".join(f'"{t}"' for t in TABLES)
                dst.execute(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE")

            for table in TABLES:
                try:
                    rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
                except sqlite3.OperationalError:
                    after = dst.execute(
                        f'SELECT COUNT(*) AS c FROM "{table}"'
                    ).fetchone()["c"]
                    report[table] = {"source": 0, "target": after, "missing": True}
                    continue

                if rows:
                    cols = list(rows[0].keys())
                    collist = ", ".join(f'"{c}"' for c in cols)
                    marks = ", ".join(["?"] * len(cols))
                    dst.executemany(
                        f'INSERT INTO "{table}" ({collist}) VALUES ({marks})'
                        " ON CONFLICT DO NOTHING",
                        [tuple(row[c] for c in cols) for row in rows],
                    )

                after = dst.execute(
                    f'SELECT COUNT(*) AS c FROM "{table}"'
                ).fetchone()["c"]
                report[table] = {"source": len(rows), "target": after}

            if report.get("job_run", {}).get("source"):
                dst.execute(
                    "SELECT setval(pg_get_serial_sequence('job_run', 'id'),"
                    " (SELECT COALESCE(MAX(id), 1) FROM job_run), true)"
                )
    finally:
        src.close()

    return report
