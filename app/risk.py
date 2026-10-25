from __future__ import annotations

import time
from typing import Any

from .ratelimit import default_client

_FAIL_KEY = "lira:risk:fail:{dims}"
_OPEN_KEY = "lira:risk:open:{dims}"

_BODY_MARKERS = (
    ("captcha", ("验证码", "captcha", "滑动验证", "安全验证")),
    ("auth_expired", ("重新登录", "登录已失效", "请登录", "login required")),
    ("forbidden", ("访问受限", "无权限", "forbidden")),
)


def classify(status_code: int | None = None, body: str = "") -> str | None:
    if status_code == 403:
        return "forbidden"
    if status_code == 429:
        return "rate_limited"
    text = (body or "").lower()
    for kind, markers in _BODY_MARKERS:
        if any(marker.lower() in text for marker in markers):
            return kind
    return None


def _dims(channel: str, account: str, shop: str) -> str:
    return f"{channel}:{account}:{shop or '-'}"


def record_failure(
    channel: str,
    account: str,
    shop: str = "",
    *,
    kind: str,
    threshold: int = 3,
    cooldown_s: float = 600,
    client: Any | None = None,
    now: float | None = None,
) -> str:
    c = client or default_client()
    dims = _dims(channel, account, shop)
    at = time.time() if now is None else now
    fail_key = _FAIL_KEY.format(dims=dims)
    open_key = _OPEN_KEY.format(dims=dims)
    count = c.incr(fail_key)
    c.expire(fail_key, int(max(cooldown_s, 60)))
    if count >= threshold:
        c.hset(open_key, mapping={"at": at, "cooldown": cooldown_s, "kind": kind})
        c.expire(open_key, int(max(cooldown_s * 2, 120)))
        return "open"
    return "closed"


def record_success(
    channel: str, account: str, shop: str = "", *, client: Any | None = None
) -> None:
    c = client or default_client()
    dims = _dims(channel, account, shop)
    c.delete(_FAIL_KEY.format(dims=dims), _OPEN_KEY.format(dims=dims))


def allow(
    channel: str,
    account: str,
    shop: str = "",
    *,
    client: Any | None = None,
    now: float | None = None,
) -> bool:
    """open 窗口内拒绝；窗口过期放行一次（半开探测），失败会立即重新打开。"""
    c = client or default_client()
    at = time.time() if now is None else now
    data = c.hgetall(_OPEN_KEY.format(dims=_dims(channel, account, shop)))
    if not data:
        return True
    return at - float(data["at"]) >= float(data["cooldown"])


def state(
    channel: str,
    account: str,
    shop: str = "",
    *,
    client: Any | None = None,
    now: float | None = None,
) -> str:
    c = client or default_client()
    at = time.time() if now is None else now
    data = c.hgetall(_OPEN_KEY.format(dims=_dims(channel, account, shop)))
    if not data:
        return "closed"
    if at - float(data["at"]) < float(data["cooldown"]):
        return "open"
    return "half_open"
