from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import agent, auth, config, llm, settings_store
from ..llm.providers import OpenAICompatProvider, ProviderError
from ..llm.types import ChatRequest, Message

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
    if body.route == "openai":
        # 旧版单通道表单与多 Provider 列表保持同步
        rows = settings_store.providers_of(current)
        active = settings_store.active_provider(current)
        if active:
            for row in rows:
                if row["id"] == active["id"]:
                    row["base_url"] = body.api_base_url or row["base_url"]
                    row["model"] = body.api_model or row["model"]
                    if body.api_key:
                        row["api_key"] = body.api_key
            settings_store.save(
                {"api_providers": rows, "active_provider": active["id"]}
            )
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


class ProbeIn(BaseModel):
    route: str | None = None


@router.post("/api/settings/models/probe")
def probe_model_call(
    body: ProbeIn | None = None,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    """发一次最小真实调用，返回模型、通道与延迟；可临时指定 route。"""
    data = settings_store.load()
    settings_store.apply({**data, "route": (body.route if body else None) or data["route"]})
    started = time.perf_counter()
    try:
        response = llm.complete(
            [{"role": "user", "content": "只回复：OK"}],
            kind="probe",
            max_tokens=12,
            temperature=0,
        )
    finally:
        settings_store.apply(data)
    latency = int((time.perf_counter() - started) * 1000)
    return {
        "ok": bool(response and response.text.strip()),
        "model": response.model if response else (
            data["local_model"] if (body.route if body else data["route"]) == "ollama" else data["api_model"]
        ),
        "provider": response.provider if response else "",
        "route": (body.route if body else data["route"]),
        "latency_ms": latency,
        "reply": (response.text.strip()[:40] if response else ""),
    }


class ProviderIn(BaseModel):
    id: str
    name: str = ""
    base_url: str
    model: str
    api_key: str | None = None
    enabled: bool = True


class ProvidersIn(BaseModel):
    providers: list[ProviderIn]
    active: str | None = None
    route: str | None = None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "-", value.strip().lower())
    return slug.strip("-")[:32] or "provider"


@router.get("/api/settings/providers")
def get_providers(actor: str = Depends(auth.require_role("admin", "manager"))) -> dict[str, Any]:
    return settings_store.public_view()


@router.post("/api/settings/providers")
def set_providers(
    body: ProvidersIn,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    current = settings_store.load()
    existing = {item["id"]: item for item in settings_store.providers_of(current)}
    rows: list[dict[str, Any]] = []
    for item in body.providers:
        pid = _slug(item.id)
        key = item.api_key or existing.get(pid, {}).get("api_key", "")
        rows.append(
            {
                "id": pid,
                "name": item.name.strip() or pid,
                "base_url": item.base_url.strip(),
                "model": item.model.strip(),
                "api_key": key,
                "enabled": bool(item.enabled),
            }
        )
    ids = {row["id"] for row in rows}
    active = body.active if body.active in ids else (rows[0]["id"] if rows else "")
    payload: dict[str, Any] = {"api_providers": rows, "active_provider": active}
    if body.route:
        payload["route"] = body.route
    else:
        selected = next((row for row in rows if row["id"] == active), None)
        if selected and selected["enabled"] and selected["api_key"]:
            payload["route"] = "openai"
    settings_store.save(payload)
    return settings_store.public_view()


@router.post("/api/settings/providers/{provider_id}/probe")
def probe_provider(
    provider_id: str,
    actor: str = Depends(auth.require_role("admin", "manager")),
) -> dict[str, Any]:
    row = next(
        (
            item
            for item in settings_store.providers_of(settings_store.load())
            if item["id"] == provider_id
        ),
        None,
    )
    if not row:
        raise HTTPException(404, "模型通道不存在")
    if not row["api_key"]:
        raise HTTPException(400, "该通道还没有配置 API Key")
    started = time.perf_counter()
    try:
        provider = OpenAICompatProvider(
            row["base_url"], row["api_key"], row["model"],
            timeout=min(20.0, config.LLM_TIMEOUT_S),
        )
        response = provider.complete(
            ChatRequest(
                messages=(Message("user", "只回复：OK"),),
                max_tokens=12,
                temperature=0,
            )
        )
        return {
            "ok": True,
            "provider": provider_id,
            "model": response.model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "reply": response.text.strip()[:40],
        }
    except ProviderError as exc:
        return {
            "ok": False,
            "provider": provider_id,
            "model": row["model"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc)[:200],
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
        "file": {"formats": ["csv", "xlsx", "xlsm", "json"], "endpoint": "/api/import/file"},
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
