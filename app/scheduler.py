from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from . import alignment, backup, config, db, outcome

log = logging.getLogger(__name__)

MODE = os.getenv("LIRA_SCHEDULER", "thread")  # celery | thread | off
ENABLED = MODE != "off"

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


def job_mapping_suggest() -> str:
    with db.get_db() as conn:
        created = alignment.auto_suggest(conn)
    return f"{created} suggestions" if created else "no suggestions"


def job_outcome_review() -> str:
    """7 天后仍未回收结果的建议：统计到期数。"""
    with db.get_db() as conn:
        rows = outcome.due_list(conn, 7)
        due = [row for row in rows if row["due"]]
    return f"{len(due)} due"


def job_backup() -> str:
    result = backup.run(config.BACKUP_KEEP)
    return f"{result['path']} ({result['size_kb']}KB, kept {result['kept']})"


def run_autopilot(limit: int = 20) -> int:
    """扫描最近未被研判的事件，交给 Agent 自动跑一轮。"""
    from . import agent_graph

    ran = 0
    since = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT e.id FROM event e"
            " LEFT JOIN suggestion s ON s.event_id = e.id"
            " WHERE e.suppressed = 0 AND s.id IS NULL AND e.ts >= ?"
            " ORDER BY e.ts DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    for row in rows:
        try:
            agent_graph.run_for_event(row["id"], trigger="scheduler")
            ran += 1
        except Exception:
            log.exception("autopilot event %s failed", row["id"])
    return ran


def job_autopilot() -> str:
    ran = run_autopilot()
    return f"{ran} events" if ran else "no events"


JOBS: dict[str, tuple[float, Callable[[], str]]] = {
    "mapping_suggest": (3600, job_mapping_suggest),
    "outcome_review": (900, job_outcome_review),
    "autopilot": (float(os.getenv("LIRA_AUTOPILOT_INTERVAL", "120")), job_autopilot),
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
    if status == "ok" and detail in ("no suggestions", "0 due"):
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


def _backup_due() -> bool:
    return _daily_due("backup", config.BACKUP_AT)


def _loop(stop: threading.Event) -> None:
    next_run = {key: 0.0 for key in JOBS}
    while not stop.is_set():
        now = time.time()
        for kind, (interval, fn) in JOBS.items():
            if now >= next_run[kind]:
                next_run[kind] = now + interval
                _run_job(kind, fn)
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
    if kind == "backup":
        fn = job_backup
    elif kind in JOBS:
        fn = JOBS[kind][1]
    else:
        raise KeyError(kind)
    _run_job(kind, fn)
    return _last.get(kind, "")
