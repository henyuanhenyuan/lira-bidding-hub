"""Ollama Provider（本地模型，离线开发与演示）。"""

from __future__ import annotations

import json
from typing import Iterator

import httpx

from ..types import ChatRequest, ChatResponse, Usage
from .base import ProviderError


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, default_model: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout

    def _payload(self, request: ChatRequest) -> dict:
        payload: dict = {
            "model": request.model or self.default_model,
            "stream": False,
            "think": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
        }
        if request.json_schema:
            payload["format"] = request.json_schema
        return payload

    def complete(self, request: ChatRequest) -> ChatResponse:
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=self._payload(request),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama 连接失败：{exc}") from exc
        if response.status_code >= 500:
            raise ProviderError(
                f"ollama {response.status_code}", status=response.status_code
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"ollama {response.status_code}: {response.text[:200]}",
                transient=False, status=response.status_code,
            )
        data = response.json()
        message = data.get("message") or {}
        return ChatResponse(
            text=str(message.get("content") or ""),
            provider=self.name,
            model=str(data.get("model") or request.model or self.default_model),
            usage=Usage(
                prompt_tokens=int(data.get("prompt_eval_count") or 0),
                completion_tokens=int(data.get("eval_count") or 0),
            ),
            raw=data,
        )

    def stream(self, request: ChatRequest) -> Iterator[str]:
        payload = {**self._payload(request), "stream": True}
        try:
            with httpx.stream(
                "POST", f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"ollama stream {response.status_code}",
                        status=response.status_code,
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = (chunk.get("message") or {}).get("content")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama stream 失败：{exc}") from exc

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return response.status_code < 400
        except httpx.HTTPError:
            return False
