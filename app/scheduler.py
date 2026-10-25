from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import (
    alignment, backup, config, connectors, db, inbox, notify, outcome, reviews,
)

log = logging.getLogger(__name__)

MODE = os.getenv("LIRA_SCHEDULER", "celery")  # celery | thread | off
ENABLED = MODE != "off"
SCAN_INTERVAL = float(os.getenv("LIRA_INBOX_INTERVAL", "15"))
DIGEST_AT = os.getenv("LIRA_DIGEST_AT", "09:00")  # 本地时间 HH:MM

_last: dict[str, str] = {}
_started_at = ""
_daily: dict[str, str] = {}
_lock = threading.Lock()


def _record(conn, kind: str, started: str, status: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO job_run (kind, started_at, finished_at, status, detail)"
        " VALUES (?,?,?,?,?)",
        (kind, started, db.now_iso(), status, detail[:500]),
    )


def job_inbox_scan() -> str:
    results = inbox.scan_once()
    if not results:
        return "no files"
    ok = sum(1 for r in results if not r.get("error") and not r.get("skipped"))
    return f"{len(results)} files, {ok} ingested"


def job_mapping_suggest() -> str:
    with db.get_db() as conn:
        created = alignment.auto_suggest(conn)
    return f"{created} suggestions" if created else "no suggestions"


def job_outcome_review() -> str:
    """7 天后仍未回收结果的建议：统计到期数，并按 20 小时去重提醒。"""
    with db.get_db() as conn:
        rows = outcome.due_list(conn, 7)
        due = [row for row in rows if row["due"]]
        sent = outcome.notify_due(conn, 7)
    return f"{len(due)} due, {sent} reminders sent"


def job_review_insight() -> str:
    with db.get_db() as conn:
        targets = [
            r["target_id"] for r in conn.execute(
                "SELECT DISTINCT target_id FROM review"
                " WHERE datetime(ts) >= datetime('now', '-7 days')"
            ).fetchall()
        ]
        done = sum(1 for t in targets if reviews.analyze(conn, t, 7))
    return f"{done} insights" if done else "no insights"


def job_connector_sync() -> str:
    if not connectors.configured():
        return "connector not configured"
    r = connectors.sync()
    return f"{r['rows_ok']} rows, {r['events_created']} events"


def job_backup() -> str:
    r = backup.run(config.BACKUP_KEEP)
    return f"{r['path']} ({r['size_kb']}KB, kept {r['kept']})"


def job_digest() -> str:
    with db.get_db() as conn:
        events = [
            {**dict(r), "evidence": db.loads(r["evidence"], [])}
            for r in conn.execute(
                "SELECT e.*, t.title AS target_title FROM event e"
                " LEFT JOIN target t ON t.id = e.target_id"
                " WHERE e.suppressed = 0 ORDER BY e.ts DESC LIMIT 10"
            ).fetchall()
        ]
        collectors = [
            dict(r) for r in conn.execute(
                "SELECT collector, COUNT(*) c, MAX(ts) last_ts FROM snapshot GROUP BY collector"
            ).fetchall()
        ]
    text = notify.digest(events, collectors)
    sent = notify.send(text)
    return f"{len(events)} events, webhook={'sent' if sent else 'skipped'}"


JOBS: dict[str, tuple[float, Callable[[], str]]] = {
    "inbox_scan": (SCAN_INTERVAL, job_inbox_scan),
    "mapping_suggest": (3600, job_mapping_suggest),
    "outcome_review": (900, job_outcome_review),
    "review_insight": (21600, job_review_insight),
    "connector_sync": (config.CONNECTOR_INTERVAL, job_connector_sync),
}


def _run_job(kind: str, fn: Callable[[], str]) -> None:
    started = db.now_iso()
    try:
        detail = fn()
        status = "ok"
    except Exception as exc:
        log.exception("job %s failed", kind)
        detail, status = str(exc), "error"
    _last[kind] = f"{started} {status}" + (f": {detail[:160]}" if status == "error" else "")
    # 空转的扫描不写日志，避免每 15 秒一条把表撑爆
    if status == "ok" and detail in (
        "no files", "no suggestions", "0 awaiting outcome", "no insights",
        "connector not configured",
    ):
        return
    try:
        with db.get_db() as conn:
            _record(conn, kind, started, status, detail)
            conn.execute(
                "DELETE FROM job_run WHERE id < (SELECT MAX(id) - 500 FROM job_run)"
            )
    except Exception:
        log.exception("failed to record job %s", kind)


def _daily_due(key: str, at: str) -> bool:
    now = datetime.now()
    if now.strftime("%H:%M") < at:
        return False
    today = now.date().isoformat()
    with _lock:
        if _daily.get(key) == today:
            return False
        _daily[key] = today
    return True


def _digest_due() -> bool:
    return _daily_due("digest", DIGEST_AT)


def _backup_due() -> bool:
    return _daily_due("backup", config.BACKUP_AT)


def _loop(stop: threading.Event) -> None:
    next_run = {k: 0.0 for k in JOBS}
    while not stop.is_set():
        now = time.time()
        for kind, (interval, fn) in JOBS.items():
            if now >= next_run[kind]:
                next_run[kind] = now + interval
                _run_job(kind, fn)
        if _digest_due():
            _run_job("digest", job_digest)
        if _backup_due():
            _run_job("backup", job_backup)
        stop.wait(1.0)


class Scheduler:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=_loop, args=(self.stop_event,), daemon=True)

    def start(self) -> None:
        global _started_at
        if not ENABLED or MODE != "thread":
            return
        if self.thread.is_alive():
            return
        _started_at = db.now_iso()
        self.thread.start()
        log.info("scheduler started")

    def stop(self) -> None:
        self.stop_event.set()


scheduler = Scheduler()


def state() -> dict:
    with db.get_db() as conn:
        runs = conn.execute(
            "SELECT kind, status, started_at, detail FROM job_run"
            " ORDER BY id DESC LIMIT 12"
        ).fetchall()
    return {
        "enabled": ENABLED,
        "mode": MODE,
        "started_at": _started_at,
        "last": dict(_last),
        "recent": [dict(r) for r in runs],
    }


def run_now(kind: str) -> str:
    if kind == "digest":
        fn = job_digest
    elif kind == "backup":
        fn = job_backup
    elif kind in JOBS:
        fn = JOBS[kind][1]
    else:
        raise KeyError(kind)
    _run_job(kind, fn)
    return _last.get(kind, "")
