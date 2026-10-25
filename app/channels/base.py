from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..contracts import SnapshotIn


@dataclass(frozen=True)
class DispatchResult:
    status: Literal["done", "pending", "skipped"]
    observations: list[SnapshotIn] = field(default_factory=list)
    external_ref: str | None = None
    detail: str = ""


class ChannelAdapter(Protocol):
    """通道只产出原始观测；写库统一走 ingest，通道自身不碰业务表。"""

    channel: str

    def dispatch(self, task: dict[str, Any]) -> DispatchResult: ...
