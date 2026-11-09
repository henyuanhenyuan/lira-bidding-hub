"""影刃 / 八爪鱼通道：拉取外部采集平台的结果，转成统一快照。

外部返回既可以是 {"snapshots": [...]}，也可以是 {"items": [...]} 或裸数组；
每条记录可以带完整 observation，也可以是扁平字段（list_price / title / region）。
"""

from __future__ import annotations

from typing import Any

import httpx

from .. import settings_store
from ..contracts import Observation, SnapshotIn
from .base import DispatchResult


def _observation(item: dict[str, Any]) -> Observation:
    if isinstance(item.get("observation"), dict):
        return Observation.model_validate(item["observation"])
    return Observation(
        list_price=item.get("list_price") or item.get("price"),
        member_price=item.get("member_price"),
        live_price=item.get("live_price"),
        coupons=item.get("coupons"),
        promotions=item.get("promotions"),
        coin=item.get("coin"),
        region=item.get("region"),
        title=item.get("title"),
        main_image_url=item.get("main_image_url"),
        stock_signal=item.get("stock_signal"),
    )


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("snapshots", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict):
                return _items(value)
    return []


def to_snapshots(payload: Any, *, target_id: str | None = None) -> list[SnapshotIn]:
    out: list[SnapshotIn] = []
    for row in _items(payload):
        data = dict(row)
        data.setdefault("target_id", target_id)
        if not data.get("target_id"):
            continue
        data.setdefault("ts", row.get("collected_at") or row.get("time"))
        data.setdefault("collector", "yingren")
        data.setdefault("source_tier", 2)
        data["observation"] = _observation(data)
        if not data.get("ts"):
            continue
        out.append(SnapshotIn.model_validate(data))
    return out


class YingrenAdapter:
    channel = "yingren"

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        data = settings_store.load()
        self.url = (url if url is not None else data.get("yingren_base_url") or "").rstrip("/")
        self.token = token if token is not None else data.get("yingren_token") or ""

    def dispatch(self, task: dict[str, Any]) -> DispatchResult:
        if not self.url:
            return DispatchResult("skipped", detail="影刃/八爪鱼 API 未配置")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = httpx.get(
            f"{self.url}/api/v1/tasks/result",
            params={"target_id": task["target_id"]},
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        observations = to_snapshots(response.json(), target_id=task["target_id"])
        return DispatchResult(
            "done", observations=observations,
            detail=f"{len(observations)} snapshots",
        )
