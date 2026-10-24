from __future__ import annotations

import json
import logging
import os

import httpx

log = logging.getLogger(__name__)

WEBHOOK = os.getenv("LIRA_WEBHOOK", "")


def enabled() -> bool:
    return bool(WEBHOOK)


def send(text: str) -> bool:
    """企业微信 / 钉钉 群机器人。未配置时静默跳过。"""
    if not WEBHOOK:
        return False
    payload = {"msgtype": "text", "text": {"content": text}}
    try:
        r = httpx.post(WEBHOOK, json=payload, timeout=8.0)
        r.raise_for_status()
        return True
    except Exception as exc:
        log.warning("webhook failed: %s", exc)
        return False


def digest(events: list[dict], collectors: list[dict]) -> str:
    lines = ["【竞品情报·今日】"]
    for c in collectors:
        lines.append(f"· 采集源 {c['collector']}：最近 {c['last_ts']}")
    if not events:
        lines.append("· 今日无重要事件")
    else:
        for e in events[:8]:
            lines.append(
                f"· [{e['severity']}] {e.get('target_title') or e['target_id']}：{e['note']}"
            )
    return "\n".join(lines)


def send_json(obj: dict) -> bool:
    if not WEBHOOK:
        return False
    try:
        httpx.post(WEBHOOK, content=json.dumps(obj, ensure_ascii=False), timeout=8.0)
        return True
    except Exception:
        return False
