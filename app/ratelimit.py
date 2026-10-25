from __future__ import annotations

import os
import time
from typing import Any

import redis

_KEY = "lira:rl:{channel}:{account}:{shop}"
_TTL_S = 3600

_ACQUIRE_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local delta = now - ts
if delta < 0 then delta = 0 end
tokens = math.min(capacity, tokens + delta * rate)
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)
return allowed
"""

_client: redis.Redis | None = None


def default_client() -> redis.Redis:
    global _client
    if _client is None:
        url = os.getenv("LIRA_REDIS_URL", "redis://127.0.0.1:6379/0")
        _client = redis.Redis.from_url(url, decode_responses=True)
    return _client


def _key(channel: str, account: str, shop: str) -> str:
    return _KEY.format(channel=channel, account=account, shop=shop or "-")


def acquire(
    channel: str,
    account: str,
    shop: str = "",
    *,
    rate: float = 1.0,
    capacity: int = 1,
    client: Any | None = None,
    now: float | None = None,
) -> bool:
    """三维令牌桶：通道 × 账号 × 店铺。rate 为每秒补充令牌数。"""
    c = client or default_client()
    at = time.time() if now is None else now
    result = c.eval(
        _ACQUIRE_LUA, 1, _key(channel, account, shop), rate, capacity, at, _TTL_S
    )
    return bool(int(result))


def wait_seconds(
    channel: str,
    account: str,
    shop: str = "",
    *,
    rate: float = 1.0,
    client: Any | None = None,
    now: float | None = None,
) -> float:
    c = client or default_client()
    tokens_raw, ts_raw = c.hmget(_key(channel, account, shop), "tokens", "ts")
    if tokens_raw is None or ts_raw is None:
        return 0.0
    at = time.time() if now is None else now
    tokens = float(tokens_raw) + max(0.0, at - float(ts_raw)) * rate
    if tokens >= 1:
        return 0.0
    return (1.0 - tokens) / rate
