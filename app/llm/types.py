"""模型网关的公共数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: tuple[Message, ...]
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 256
    json_schema: dict[str, Any] | None = None
    stream: bool = False


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ChatResponse:
    text: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    raw: dict[str, Any] | None = None


StreamChunk = str
Stream = Iterator[str]
