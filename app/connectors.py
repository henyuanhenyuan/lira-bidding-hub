from __future__ import annotations

import os
import threading
import time

import httpx

from . import db, ingest
from .contracts import IngestBatch

URL = os.getenv("LIRA_CONNECTOR_URL", "")
TOKEN = os.getenv("LIRA_CONNECTOR_TOKEN", "")
MAX_PER_MIN = int(os.getenv("LIRA_CONNECTOR_RPM", "60"))

_lock = threading.Lock()
_window: list[float] = []


def configured() -> bool:
    return bool(URL)


def _allow() -> bool:
    """滑动窗口限流：连接器最多 60 次/分钟。"""
    now = time.time()
    with _lock:
        _window[:] = [t for t in _window if now - t < 60]
        if len(_window) >= MAX_PER_MIN:
            return False
        _window.append(now)
        return True


def sync() -> dict:
    if not configured():
        return {"skipped": True, "reason": "LIRA_CONNECTOR_URL 未配置"}
    if not _allow():
        raise RuntimeError("连接器触发限流（60 次/分钟）")

    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    r = httpx.get(URL, headers=headers, timeout=30.0)
    r.raise_for_status()

    payload = r.json()
    batch = IngestBatch(**payload)
    with db.get_db() as conn:
        report = ingest.ingest(conn, batch.snapshots, source="connector", file_name="api")
    out = report.as_dict()
    out["skipped"] = False
    return out
