"""多 Provider 路由：按任务类型选通道，失败降级 + 退避 + 熔断 + 限流。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from .limiter import RateLimiter
from .providers.base import Provider, ProviderError
from .types import ChatRequest, ChatResponse

log = logging.getLogger(__name__)


class RateLimited(RuntimeError):
    """本进程触发每请求限流。"""


@dataclass
class _Breaker:
    threshold: int = 3
    cooldown: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    clock: Callable[[], float] = time.monotonic

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if self.clock() - self.opened_at >= self.cooldown:
            self.opened_at = None
            self.failures = 0
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = self.clock()


@dataclass
class Router:
    providers: dict[str, Provider]
    chains: dict[str, list[str]]
    limiter: RateLimiter
    breakers: dict[str, _Breaker] = field(default_factory=dict)
    max_retries: int = 2
    backoff: float = 0.4
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        for name in self.providers:
            self.breakers.setdefault(name, _Breaker())

    def _chain(self, kind: str) -> list[str]:
        chain = self.chains.get(kind) or self.chains.get("default") or []
        return [name for name in chain if name in self.providers]

    def complete(self, kind: str, request: ChatRequest) -> ChatResponse:
        chain = self._chain(kind)
        if not chain:
            raise ProviderError("没有可用的模型通道", transient=False)
        errors: list[str] = []
        for name in chain:
            breaker = self.breakers[name]
            if not breaker.allow():
                errors.append(f"{name}: 熔断中")
                continue
            for attempt in range(self.max_retries + 1):
                if not self.limiter.allow():
                    raise RateLimited("模型调用触发每请求限流")
                try:
                    response = self.providers[name].complete(request)
                    breaker.success()
                    return response
                except ProviderError as exc:
                    breaker.failure()
                    errors.append(f"{name}: {exc}")
                    if exc.transient and attempt < self.max_retries:
                        self.sleep(self.backoff * (2 ** attempt))
                        continue
                    break
        raise ProviderError("所有模型通道不可用：" + "；".join(errors), transient=False)

    def stream(self, kind: str, request: ChatRequest) -> Iterator[str]:
        chain = self._chain(kind)
        last: Exception | None = None
        for name in chain:
            if not self.breakers[name].allow():
                continue
            if not self.limiter.allow():
                raise RateLimited("模型调用触发每请求限流")
            started = False
            try:
                for piece in self.providers[name].stream(request):
                    started = True
                    yield piece
                self.breakers[name].success()
                return
            except ProviderError as exc:
                self.breakers[name].failure()
                last = exc
                if started or not exc.transient:
                    break
                continue
        raise ProviderError(f"流式调用失败：{last}", transient=False)
