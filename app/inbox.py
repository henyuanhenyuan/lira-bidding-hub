from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config, csvimport, db, ingest, stream
from .contracts import IngestBatch

log = logging.getLogger(__name__)

SUFFIXES = {".csv", ".json"}

# 后台线程与手动触发可能同时扫描，必须串行
_scan_lock = threading.Lock()


def inbox_dir() -> Path:
    d = config.DATA_DIR / "inbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _processed_dir() -> Path:
    d = inbox_dir() / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _failed_dir() -> Path:
    d = inbox_dir() / "failed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _already_done(conn, name: str, digest: str) -> bool:
    row = conn.execute(
        "SELECT status, content_hash FROM inbox_file WHERE name = ?", (name,)
    ).fetchone()
    return bool(row and row["status"] == "ingested" and row["content_hash"] == digest)


def _record(conn, name: str, digest: str, status: str, report=None, error=None) -> None:
    conn.execute(
        "INSERT INTO inbox_file (name, content_hash, status, rows_ok,"
        " rows_dup, rows_rejected, error, processed_at) VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT (name) DO UPDATE SET content_hash=excluded.content_hash,"
        " status=excluded.status, rows_ok=excluded.rows_ok, rows_dup=excluded.rows_dup,"
        " rows_rejected=excluded.rows_rejected, error=excluded.error,"
        " processed_at=excluded.processed_at",
        (
            name, digest, status,
            report.rows_ok if report else 0,
            report.rows_dup if report else 0,
            report.rows_rejected if report else 0,
            error, db.now_iso(),
        ),
    )


def ingest_file(path: Path) -> dict:
    name = path.name
    digest = _file_hash(path)

    with db.get_db() as conn:
        if _already_done(conn, name, digest):
            return {"file": name, "skipped": True}

    try:
        snaps, parse_errors = _parse(path)
        if not snaps and parse_errors:
            raise ValueError(f"no valid rows: {parse_errors[0]['error']}")
        with db.get_db() as conn:
            report = ingest.ingest(
                conn, snaps, source=f"inbox:{path.suffix[1:]}", file_name=name
            )
            failed = report.rows_ok == 0 and report.rows_rejected > 0
            _record(
                conn, name, digest, "failed" if failed else "ingested",
                report=report, error="all rows rejected" if failed else None,
            )
        target_dir = _failed_dir() if failed else _processed_dir()
        try:
            shutil.move(str(path), str(target_dir / name))
        except FileNotFoundError:
            pass  # 另一个线程已处理同一文件
        out = {"file": name, **report.as_dict()}
        if parse_errors:
            out["errors"] = parse_errors + out["errors"]
            out["rows_rejected"] += len(parse_errors)
        stream.publish("ingest", {
            "file": name, "rows_ok": report.rows_ok,
            "events_created": report.events_created,
        })
        return out
    except Exception as exc:
        log.warning("inbox file failed: %s (%s)", name, exc)
        with db.get_db() as conn:
            _record(conn, name, digest, "failed", error=str(exc))
        try:
            shutil.move(str(path), str(_failed_dir() / name))
        except OSError:
            pass
        return {"file": name, "error": str(exc)}


def _parse(path: Path):
    raw = path.read_bytes()
    errors: list[dict] = []
    if path.suffix.lower() == ".csv":
        snaps, errors = csvimport.parse_csv_bytes(raw)
    else:
        data = json.loads(raw.decode("utf-8"))
        batch = IngestBatch(**data)
        snaps = batch.snapshots
    return snaps, errors


def scan_once() -> list[dict]:
    results: list[dict] = []
    with _scan_lock:
        for path in sorted(inbox_dir().iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                continue
            results.append(ingest_file(path))
    return results


def pending_count() -> int:
    return sum(
        1 for p in inbox_dir().iterdir()
        if p.is_file() and p.suffix.lower() in SUFFIXES
    )


def failed_files(limit: int = 10) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(_failed_dir().iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        stat = p.stat()
        rows.append({
            "name": p.name,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        })
        if len(rows) >= limit:
            break
    return rows


def failed_count() -> int:
    return sum(1 for p in _failed_dir().iterdir() if p.is_file())
