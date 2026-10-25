from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config, db
from .base import DispatchResult


class YingdaoAdapter:
    """影刀通道：写工单文件，由影刀计划任务消费；结果经 inbox 或 ingest 回来。"""

    channel = "rpa"

    def __init__(self, outbox: Path | None = None) -> None:
        self.outbox = Path(outbox) if outbox is not None else config.DATA_DIR / "collect_outbox"

    def dispatch(self, task: dict[str, Any]) -> DispatchResult:
        self.outbox.mkdir(parents=True, exist_ok=True)
        name = f"{task['id']}.json"
        payload = {
            "task_id": task["id"],
            "target_id": task["target_id"],
            "channel": self.channel,
            "priority": task.get("priority", 0),
            "created_at": db.now_iso(),
        }
        (self.outbox / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return DispatchResult("pending", external_ref=name, detail="已下发影刀工单")
