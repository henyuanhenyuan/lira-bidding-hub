"""运行时设置：模型走本地还是云端，可在设置页切换并持久化。

密钥只写在 `data/settings.json`（data/ 已在 .gitignore 中），不入库、不进日志。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config

SETTINGS_PATH = Path(config.DATA_DIR) / "settings.json"

DEFAULTS: dict[str, Any] = {
    "backend": "gateway",
    "route": "ollama",
    "local_model": "qwen3:4b",
    "local_url": "http://127.0.0.1:11434",
    "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_model": "qwen-plus",
    "api_key": "",
    "active_provider": "qwen",
    "api_providers": [
        {
            "id": "qwen", "name": "通义千问",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus", "api_key": "", "enabled": True,
        },
    ],
    "taobao_app_key": "",
    "taobao_app_secret": "",
    "octoparse_token": "",
    "octoparse_base_url": "https://dataapi.octoparse.com",
    "yingren_base_url": "",
    "yingren_token": "",
    "native_crawler_url": "",
    "native_crawler_token": "",
    # 自主竞价
    "autopilot_enabled": True,
    "autopilot_strategy": "follow",
    "autopilot_undercut_pct": 0.02,
    "autopilot_max_delta_pct": 0.15,
    "autopilot_min_confidence": 0.80,
}


def load() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **{key: data[key] for key in DEFAULTS if key in data}}


def save(values: dict[str, Any]) -> dict[str, Any]:
    merged = {**load(), **{key: values[key] for key in DEFAULTS if key in values}}
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    apply(merged)
    return merged


def providers_of(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = (data or load()).get("api_providers") or []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "").strip()
        if not pid:
            continue
        cleaned.append(
            {
                "id": pid,
                "name": str(row.get("name") or pid),
                "base_url": str(row.get("base_url") or "").strip(),
                "model": str(row.get("model") or "").strip(),
                "api_key": str(row.get("api_key") or ""),
                "enabled": bool(row.get("enabled", True)),
            }
        )
    return cleaned


def active_provider(data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = data or load()
    providers = providers_of(data)
    wanted = str(data.get("active_provider") or "")
    for provider in providers:
        if provider["id"] == wanted:
            return provider
    for provider in providers:
        if provider["enabled"] and provider["api_key"]:
            return provider
    return providers[0] if providers else None


def apply(values: dict[str, Any] | None = None) -> None:
    """把设置写进 config，使其在当前进程立即生效。"""
    data = values or load()
    config.LLM_BACKEND = data.get("backend") or config.LLM_BACKEND
    config.LLM_ROUTE = data.get("route") or config.LLM_ROUTE
    config.OLLAMA_MODEL = data.get("local_model") or config.OLLAMA_MODEL
    config.OLLAMA_URL = data.get("local_url") or config.OLLAMA_URL

    providers = providers_of(data)
    config.OPENAI_PROVIDERS = [
        {
            "id": item["id"], "name": item["name"],
            "base_url": item["base_url"], "model": item["model"],
            "api_key": item["api_key"],
        }
        for item in providers
        if item["enabled"] and item["base_url"] and item["api_key"]
    ]

    active = active_provider(data)
    if active and active["api_key"] and active["base_url"]:
        config.OPENAI_BASE_URL = active["base_url"]
        config.OPENAI_MODEL = active["model"] or config.OPENAI_MODEL
        config.OPENAI_API_KEY = active["api_key"]
    else:
        config.OPENAI_BASE_URL = data.get("api_base_url") or ""
        config.OPENAI_MODEL = data.get("api_model") or config.OPENAI_MODEL
        config.OPENAI_API_KEY = data.get("api_key") or ""


def public_view() -> dict[str, Any]:
    data = load()
    providers = providers_of(data)
    active = active_provider(data)
    api_base = (active["base_url"] if active else "") or data["api_base_url"]
    api_model = (active["model"] if active else "") or data["api_model"]
    api_key = bool(active and active["api_key"]) or bool(data["api_key"])
    return {
        "backend": data["backend"],
        "route": data["route"],
        "local": {"model": data["local_model"], "url": data["local_url"]},
        "api": {
            "base_url": api_base,
            "model": api_model,
            "has_key": api_key,
        },
        "active_provider": active["id"] if active else data.get("active_provider"),
        "providers": [
            {
                "id": item["id"],
                "name": item["name"],
                "base_url": item["base_url"],
                "model": item["model"],
                "enabled": item["enabled"],
                "has_key": bool(item["api_key"]),
            }
            for item in providers
        ],
        "judge_model": config.JUDGE_MODEL,
        "sources": {
            "taobao": {
                "app_key": data["taobao_app_key"],
                "has_secret": bool(data["taobao_app_secret"]),
            },
            "octoparse": {
                "base_url": data["octoparse_base_url"],
                "has_token": bool(data["octoparse_token"]),
            },
            "yingren": {
                "base_url": data["yingren_base_url"],
                "has_token": bool(data["yingren_token"]),
            },
            "native": {
                "base_url": data["native_crawler_url"],
                "has_token": bool(data["native_crawler_token"]),
            },
        },
        "autopilot": {
            "enabled": bool(data["autopilot_enabled"]),
            "strategy": data["autopilot_strategy"],
            "undercut_pct": data["autopilot_undercut_pct"],
            "max_delta_pct": data["autopilot_max_delta_pct"],
            "min_confidence": data["autopilot_min_confidence"],
        },
    }
