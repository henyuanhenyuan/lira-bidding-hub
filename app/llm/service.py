"""网关入口：构造 Router、记录指标、对上层屏蔽异常。

约定：任何失败都返回 None（或空流），由调用方回落到确定性模板——
与 `LIRA_LLM=off` 时的行为保持一致。
"""

from __future__ import annotations

import os
import time
from typing import Iterator, Sequence

from .. import config, metrics
from ..prompts import registry as prompt_registry
from . import ledger
from .limiter import get_limiter
from .providers import OllamaProvider, OpenAICompatProvider, ProviderError
from .router import RateLimited, Router
from .types import ChatRequest, ChatResponse, Message


def backend() -> str:
    return os.getenv("LIRA_LLM_BACKEND", config.LLM_BACKEND)


def gateway_enabled() -> bool:
    return backend() == "gateway"


def _api_names() -> list[str]:
    return [f"api:{item['id']}" for item in getattr(config, "OPENAI_PROVIDERS", [])]


def _build_providers() -> dict:
    providers: dict = {}
    for item in getattr(config, "OPENAI_PROVIDERS", []):
        providers[f"api:{item['id']}"] = OpenAICompatProvider(
            item["base_url"], item["api_key"], item["model"],
            timeout=config.LLM_TIMEOUT_S,
        )
    if not providers and config.OPENAI_BASE_URL and config.OPENAI_API_KEY:
        providers["openai"] = OpenAICompatProvider(
            config.OPENAI_BASE_URL, config.OPENAI_API_KEY, config.OPENAI_MODEL,
            timeout=config.LLM_TIMEOUT_S,
        )
    providers["ollama"] = OllamaProvider(
        config.OLLAMA_URL, config.OLLAMA_MODEL, timeout=config.LLM_TIMEOUT_S,
    )
    return providers


def _chains(names: Sequence[str]) -> dict[str, list[str]]:
    api = _api_names()
    route = config.LLM_ROUTE
    provider_ids = {item["id"] for item in getattr(config, "OPENAI_PROVIDERS", [])}
    if route == "ollama":
        order = ["ollama"]
    elif route.startswith("api:") and route in api:
        order = [route]
    elif route in provider_ids:
        order = [f"api:{route}"]
    elif route == "openai":
        order = api or (
            ["openai"] if config.OPENAI_BASE_URL and config.OPENAI_API_KEY else ["ollama"]
        )
    elif route == "auto":
        order = api + ["ollama"]
    elif not api and not config.OPENAI_BASE_URL:
        order = ["ollama"]
    else:
        order = list(names) or api + ["ollama"]
    return {
        "default": order, "analysis": order,
        "critic": order, "judge": order, "review_summary": order,
    }


def build_router() -> Router:
    return Router(
        providers=_build_providers(),
        chains=_chains([]),
        limiter=get_limiter(config.LLM_RPM),
        max_retries=config.LLM_MAX_RETRIES,
    )


def _messages(messages: Sequence[Message] | Sequence[dict]) -> tuple[Message, ...]:
    out: list[Message] = []
    for item in messages:
        if isinstance(item, Message):
            out.append(item)
        else:
            out.append(Message(str(item.get("role", "user")), str(item.get("content", ""))))
    return tuple(out)


def _record(kind: str, prompt_name: str, response: ChatResponse, started: float) -> None:
    metrics.record(
        kind,
        model=response.model,
        ok=True,
        latency_ms=int((time.perf_counter() - started) * 1000),
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        provider=response.provider,
        prompt_name=prompt_name,
        prompt_version=prompt_registry.version_of(prompt_name),
        cost=ledger.cost(
            response.model, response.usage.prompt_tokens, response.usage.completion_tokens
        ),
    )


def complete(
    messages: Sequence[Message] | Sequence[dict],
    *,
    kind: str = "analysis",
    prompt_name: str | None = None,
    schema: dict | None = None,
    model: str = "",
    max_tokens: int = 256,
    temperature: float = 0.0,
) -> ChatResponse | None:
    name = prompt_name or kind
    started = time.perf_counter()
    try:
        response = build_router().complete(
            kind,
            ChatRequest(
                messages=_messages(messages),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_schema=schema,
            ),
        )
    except (ProviderError, RateLimited) as exc:
        metrics.record(
            kind, model=model or config.OLLAMA_MODEL, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            provider="", prompt_name=name,
            prompt_version=prompt_registry.version_of(name),
            detail=str(exc),
        )
        return None
    _record(kind, name, response, started)
    return response


def stream(
    messages: Sequence[Message] | Sequence[dict],
    *,
    kind: str = "analysis",
    prompt_name: str | None = None,
    schema: dict | None = None,
    model: str = "",
    max_tokens: int = 256,
    temperature: float = 0.0,
) -> Iterator[str]:
    try:
        yield from build_router().stream(
            kind,
            ChatRequest(
                messages=_messages(messages),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_schema=schema,
                stream=True,
            ),
        )
    except (ProviderError, RateLimited):
        return
