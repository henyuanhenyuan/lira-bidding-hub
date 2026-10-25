from __future__ import annotations

import os
from typing import Any

import httpx

from ..contracts import IngestBatch
from .base import DispatchResult


class ApiAdapter:
    channel = "api"

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        self.url = os.getenv("LIRA_CONNECTOR_URL", "") if url is None else url
        self.token = os.getenv("LIRA_CONNECTOR_TOKEN", "") if token is None else token

    def dispatch(self, task: dict[str, Any]) -> DispatchResult:
        if not self.url:
            return DispatchResult("skipped", detail="LIRA_CONNECTOR_URL 未配置")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = httpx.get(
            self.url,
            params={"target_id": task["target_id"]},
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        batch = IngestBatch(**response.json())
        return DispatchResult("done", observations=batch.snapshots)
