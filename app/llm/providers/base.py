"""Provider 协议与错误类型。"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from ..types import ChatRequest, ChatResponse


class ProviderError(RuntimeError):
    """transient=True 表示可重试/可降级（超时、429、5xx）。"""

    def __init__(self, message: str, *, transient: bool = True, status: int | None = None):
        super().__init__(message)
        self.transient = transient
        self.status = status


@runtime_checkable
class Provider(Protocol):
    name: str

    def complete(self, request: ChatRequest) -> ChatResponse: ...

    def stream(self, request: ChatRequest) -> Iterator[str]: ...

    def health(self) -> bool: ...
