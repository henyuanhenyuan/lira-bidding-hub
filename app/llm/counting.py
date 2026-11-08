"""粗略 token 估算：中文按字、英文按词，用于预算与截断。

不引入 tiktoken 之类的重依赖；误差在 10% 量级，足够做预算控制。
"""

from __future__ import annotations

import re

_CJK = re.compile(r"[一-鿿　-〿＀-￯]")
_WORD = re.compile(r"[A-Za-z0-9_]+")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    other = max(0, len(text) - cjk - len("".join(_WORD.findall(text))))
    return max(1, cjk + words + other // 4)


def count_messages(messages) -> int:
    total = 0
    for message in messages:
        total += estimate_tokens(message.content) + 4
    return total


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """从尾部截断，保留开头（通常是指令与关键事实）。"""
    if max_tokens <= 0 or estimate_tokens(text) <= max_tokens:
        return text
    ratio = max_tokens / max(1, estimate_tokens(text))
    return text[: max(1, int(len(text) * ratio))]
