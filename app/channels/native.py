"""自有爬虫通道：优先调用自建爬虫服务，未配置时用 Playwright 直采。

自建服务契约与影刃一致；直采模式依赖任务里的 url 与 price_selector。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .. import settings_store
from ..contracts import Observation, SnapshotIn
from .base import DispatchResult
from .yingren import to_snapshots


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _price(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else None


class NativeAdapter:
    channel = "native"

    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        data = settings_store.load()
        self.url = (url if url is not None else data.get("native_crawler_url") or "").rstrip("/")
        self.token = token if token is not None else data.get("native_crawler_token") or ""

    def dispatch(self, task: dict[str, Any]) -> DispatchResult:
        if self.url:
            return self._remote(task)
        return self._playwright(task)

    def _remote(self, task: dict[str, Any]) -> DispatchResult:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = httpx.get(
            f"{self.url}/fetch",
            params={"target_id": task["target_id"], "url": task.get("url") or ""},
            headers=headers,
            timeout=60.0,
        )
        response.raise_for_status()
        observations = to_snapshots(response.json(), target_id=task["target_id"])
        for snap in observations:
            snap.collector = "native"
            snap.source_tier = 1
        return DispatchResult("done", observations=observations)

    def _playwright(self, task: dict[str, Any]) -> DispatchResult:
        url = task.get("url") or ""
        if not url:
            return DispatchResult("skipped", detail="未配置自有爬虫，且任务缺少商品 URL")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return DispatchResult(
                "skipped", detail="Playwright 未安装：pip install playwright && playwright install chromium"
            )
        selector = task.get("price_selector") or "meta[itemprop='price']"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                element = page.query_selector(selector)
                raw = ""
                if element:
                    raw = element.get_attribute("content") or element.inner_text()
                if not raw:
                    raw = page.inner_text("body")[:2000]
                title = page.title()
            finally:
                browser.close()

        price = _price(raw)
        if price is None:
            return DispatchResult("skipped", detail="页面未解析到价格")
        snap = SnapshotIn(
            target_id=task["target_id"], ts=_now(), collector="native", source_tier=1,
            observation=Observation(list_price=price, title=title),
        )
        return DispatchResult("done", observations=[snap], detail=f"price={price}")
