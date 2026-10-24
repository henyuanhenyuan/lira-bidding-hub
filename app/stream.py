from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_subscribers: set[queue.Queue] = set()
_counter = 0


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=100)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        _subscribers.discard(q)


def publish(kind: str, data: dict[str, Any]) -> None:
    """进程内广播。单进程部署有效；多 worker 需换 Redis pub/sub。"""
    global _counter
    with _lock:
        _counter += 1
        payload = {
            "id": _counter,
            "kind": kind,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": data,
        }
        dead: list[queue.Queue] = []
        for q in _subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _subscribers.discard(q)


def format_sse(payload: dict[str, Any]) -> str:
    return (
        f"id: {payload['id']}\n"
        f"event: {payload['kind']}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )
