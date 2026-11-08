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
    "route": "auto",
    "local_model": "qwen3:4b",
    "local_url": "http://127.0.0.1:11434",
    "api_base_url": "",
    "api_model": "qwen-plus",
    "api_key": "",
    "taobao_app_key": "",
    "taobao_app_secret": "",
    "octoparse_token": "",
    "octoparse_base_url": "https://dataapi.octoparse.com",
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


def apply(values: dict[str, Any] | None = None) -> None:
    """把设置写进 config，使其在当前进程立即生效。"""
    data = values or load()
    config.LLM_BACKEND = data.get("backend") or config.LLM_BACKEND
    config.LLM_ROUTE = data.get("route") or config.LLM_ROUTE
    config.OLLAMA_MODEL = data.get("local_model") or config.OLLAMA_MODEL
    config.OLLAMA_URL = data.get("local_url") or config.OLLAMA_URL
    config.OPENAI_BASE_URL = data.get("api_base_url") or ""
    config.OPENAI_MODEL = data.get("api_model") or config.OPENAI_MODEL
    config.OPENAI_API_KEY = data.get("api_key") or ""


def public_view() -> dict[str, Any]:
    data = load()
    return {
        "backend": data["backend"],
        "route": data["route"],
        "local": {"model": data["local_model"], "url": data["local_url"]},
        "api": {
            "base_url": data["api_base_url"],
            "model": data["api_model"],
            "has_key": bool(data["api_key"]),
        },
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
        },
    }
