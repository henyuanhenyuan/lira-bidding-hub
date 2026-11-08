from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import agent, auth, settings_store

router = APIRouter()


class ModelSettings(BaseModel):
    backend: str = "gateway"
    route: str = "auto"
    local_model: str = "qwen3:4b"
    local_url: str = "http://127.0.0.1:11434"
    api_base_url: str = ""
    api_model: str = "qwen-plus"
    api_key: str | None = None


@router.get("/api/settings/models")
def get_models(actor: str = Depends(auth.require_role("admin", "manager"))) -> dict[str, Any]:
    return settings_store.public_view()


@router.post("/api/settings/models")
def set_models(
    body: ModelSettings,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    current = settings_store.load()
    payload = body.model_dump()
    if not payload.get("api_key"):
        # 空值表示沿用已保存的密钥
        payload["api_key"] = current.get("api_key", "")
    settings_store.save(payload)
    return settings_store.public_view()


@router.get("/api/settings/models/probe")
def probe_models(
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    settings_store.apply()
    return {
        "llm_available": agent._llm_available(),
        "backend": settings_store.load()["backend"],
        "route": settings_store.load()["route"],
    }


class SourceSettings(BaseModel):
    taobao_app_key: str | None = None
    taobao_app_secret: str | None = None
    octoparse_token: str | None = None
    octoparse_base_url: str | None = None


@router.get("/api/settings/sources")
def get_sources(actor: str = Depends(auth.require_role("admin", "manager"))) -> dict[str, Any]:
    """数据接入：淘宝开放平台、影刃八爪鱼，以及推送/文件入口。"""
    import os

    view = settings_store.public_view()
    return {
        **view["sources"],
        "ingest": {
            "url": "/v1/ingest/snapshots",
            "has_token": bool(os.getenv("LIRA_INGEST_TOKEN", "")),
        },
        "file": {"formats": ["csv", "json"], "endpoint": "/api/import/file"},
    }


@router.post("/api/settings/sources")
def set_sources(
    body: SourceSettings,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    current = settings_store.load()
    payload = {
        "taobao_app_key": body.taobao_app_key or current["taobao_app_key"],
        "taobao_app_secret": body.taobao_app_secret or current["taobao_app_secret"],
        "octoparse_token": body.octoparse_token or current["octoparse_token"],
        "octoparse_base_url": body.octoparse_base_url or current["octoparse_base_url"],
    }
    settings_store.save(payload)
    return get_sources(actor)
