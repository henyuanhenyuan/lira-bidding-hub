from __future__ import annotations

from .api import ApiAdapter
from .base import ChannelAdapter, DispatchResult
from .manual import ManualAdapter
from .native import NativeAdapter
from .yingren import YingrenAdapter

_ADAPTERS: dict[str, type[ChannelAdapter]] = {
    "api": ApiAdapter,
    "manual": ManualAdapter,
    "yingren": YingrenAdapter,
    "native": NativeAdapter,
}


def get_adapter(channel: str) -> ChannelAdapter:
    try:
        factory = _ADAPTERS[channel]
    except KeyError as exc:
        raise ValueError(f"unknown channel: {channel}") from exc
    return factory()


__all__ = [
    "ApiAdapter",
    "ChannelAdapter",
    "DispatchResult",
    "ManualAdapter",
    "NativeAdapter",
    "YingrenAdapter",
    "get_adapter",
]
