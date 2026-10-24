from __future__ import annotations

import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from . import config, db


def backup_dir() -> Path:
    d = config.DATA_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _archive_inbox(target: Path, stamp: str) -> None:
    inbox = config.DATA_DIR / "inbox"
    if inbox.exists():
        shutil.make_archive(str(target / f"inbox-{stamp}"), "zip", inbox)


def _cleanup(target: Path, pattern: str, keep: int) -> tuple[int, int]:
    files = sorted(target.glob(pattern), reverse=True)
    removed = 0
    for old in files[keep:]:
        old.unlink(missing_ok=True)
        removed += 1
    return len(files) - removed, removed


def _pg_dump_fallback(out: Path) -> None:
    """没有 pg_dump 时的纯 Python 逻辑备份：schema + COPY 数据。"""
    import psycopg

    from .migrate import TABLES

    with psycopg.connect(db.DATABASE_URL) as conn:
        with out.open("w", encoding="utf-8") as fh:
            for statement in db._pg_schema():
                fh.write(statement + ";\n")
            fh.write("\n")
            for table in TABLES:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT * FROM "{table}" LIMIT 0')
                    cols = [d.name for d in cur.description]
                collist = ", ".join(f'"{c}"' for c in cols)
                fh.write(f'COPY "{table}" ({collist}) FROM stdin;\n')
                with conn.cursor() as cur:
                    with cur.copy(f'COPY "{table}" ({collist}) TO STDOUT') as cp:
                        for block in cp:
                            fh.write(bytes(block).decode("utf-8"))
                fh.write("\\.\n\n")


def run(keep: int = 7, target_dir: Path | None = None) -> dict:
    """在线备份 + 收件箱归档 + 旧备份清理。PG 用 pg_dump，SQLite 用 backup API。"""
    target = Path(target_dir) if target_dir else backup_dir()
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if db.BACKEND == "postgres":
        out = target / f"lira-{stamp}.sql"
        pg_dump = shutil.which("pg_dump")
        if pg_dump:
            subprocess.run(
                [pg_dump, "--no-owner", "--no-acl", "--file", str(out), db.DATABASE_URL],
                check=True,
            )
        else:
            _pg_dump_fallback(out)
        _archive_inbox(target, stamp)
        kept, removed = _cleanup(target, "lira-*.sql", keep)
        return {
            "path": str(out),
            "size_kb": round(out.stat().st_size / 1024, 1) if out.exists() else 0,
            "kept": kept,
            "removed": removed,
        }

    out = target / f"lira-{stamp}.db"
    if config.DB_PATH.exists():
        src = sqlite3.connect(config.DB_PATH)
        dst = sqlite3.connect(out)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()

    _archive_inbox(target, stamp)
    kept, removed = _cleanup(target, "lira-*.db", keep)
    return {
        "path": str(out),
        "size_kb": round(out.stat().st_size / 1024, 1) if out.exists() else 0,
        "kept": kept,
        "removed": removed,
    }
