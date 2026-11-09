from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import config, db


def backup_dir() -> Path:
    d = config.DATA_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


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

    with psycopg.connect(db.DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " ORDER BY tablename"
            )
            tables = [row[0] for row in cur.fetchall()]
        with out.open("w", encoding="utf-8") as fh:
            for statement in db._pg_schema():
                fh.write(statement + ";\n")
            fh.write("\n")
            for table in tables:
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
    """在线备份 + 收件箱归档 + 旧备份清理。"""
    target = Path(target_dir) if target_dir else backup_dir()
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    out = target / f"lira-{stamp}.sql"
    pg_dump = shutil.which("pg_dump")
    if pg_dump:
        subprocess.run(
            [pg_dump, "--no-owner", "--no-acl", "--file", str(out), db.DATABASE_URL],
            check=True,
        )
    else:
        _pg_dump_fallback(out)
    kept, removed = _cleanup(target, "lira-*.sql", keep)
    return {
        "path": str(out),
        "size_kb": round(out.stat().st_size / 1024, 1) if out.exists() else 0,
        "kept": kept,
        "removed": removed,
    }
