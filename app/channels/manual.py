from __future__ import annotations

from typing import Any

from .base import DispatchResult


class ManualAdapter:
    """人工通道：不主动抓取，等待文件投递到 data/inbox/。"""

    channel = "manual"

    def dispatch(self, task: dict[str, Any]) -> DispatchResult:
        return DispatchResult("pending", detail="等待人工文件投递到 inbox")
