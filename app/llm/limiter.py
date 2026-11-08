"""每请求限流（区别于每日 token 预算）。进程内令牌桶，多进程部署时各进程独立。"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, rpm: int = 60, clock=time.monotonic) -> None:
        self.rpm = max(1, int(rpm))
        self._interval = 60.0 / self.rpm
        self._clock = clock
        self._next_at = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = self._clock()
            if now < self._next_at:
                return False
            self._next_at = now + self._interval
            return True

    def wait_seconds(self) -> float:
        with self._lock:
            return max(0.0, self._next_at - self._clock())

    def reset(self) -> None:
        with self._lock:
            self._next_at = 0.0


_limiters: dict[int, RateLimiter] = {}
_global_lock = threading.Lock()


def get_limiter(rpm: int) -> RateLimiter:
    with _global_lock:
        if rpm not in _limiters:
            _limiters[rpm] = RateLimiter(rpm)
        return _limiters[rpm]
