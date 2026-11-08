"""OpenAI 兼容通道：DashScope(qwen-plus)、DeepSeek 等。"""

from __future__ import annotations

import json
from typing import Iterator

import httpx

from ..types import ChatRequest, ChatResponse, Usage
from .base import ProviderError


class OpenAICompatProvider:
    name = "openai"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ChatRequest) -> dict:
        payload: dict = {
            "model": request.model or self.default_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.json_schema:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def complete(self, request: ChatRequest) -> ChatResponse:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai 兼容通道连接失败：{exc}") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise ProviderError(
                f"openai 兼容通道 {response.status_code}",
                status=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"openai 兼容通道 {response.status_code}: {response.text[:200]}",
                transient=False, status=response.status_code,
            )
        data = response.json()
        choices = data.get("choices") or []
        text = ""
        if choices:
            text = ((choices[0].get("message") or {}).get("content") or "")
        usage = data.get("usage") or {}
        return ChatResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or request.model or self.default_model),
            usage=Usage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            ),
            raw=data,
        )

    def stream(self, request: ChatRequest) -> Iterator[str]:
        payload = {**self._payload(request), "stream": True}
        try:
            with httpx.stream(
                "POST", f"{self.base_url}/chat/completions",
                headers=self._headers(), json=payload, timeout=self.timeout,
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError(
                        f"openai 兼容通道 stream {response.status_code}",
                        status=response.status_code,
                    )
                for line in response.iter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        chunk = json.loads(body)
                    except ValueError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    piece = (choices[0].get("delta") or {}).get("content")
                    if piece:
                        yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai 兼容通道 stream 失败：{exc}") from exc

    def health(self) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/models", headers=self._headers(), timeout=3.0
            )
            return response.status_code < 400
        except httpx.HTTPError:
            return False
