"""PII 脱敏：出站到模型、写入日志/指标前调用。"""

from __future__ import annotations

import re
from typing import Any

PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证]"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "[银行卡]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[邮箱]"),
    (re.compile(r"[一-龥]{2,8}(省|市)[一-龥]{1,10}(区|县|市)[一-龥]{0,20}"
                r"(路|街|道|巷)[一-龥\d]{0,10}号?"), "[地址]"),
)


def redact(text: str) -> tuple[str, int]:
    if not text:
        return text, 0
    count = 0
    result = text
    for pattern, replacement in PATTERNS:
        result, hits = pattern.subn(replacement, result)
        count += hits
    return result, count


def redact_deep(value: Any) -> Any:
    """递归脱敏 dict / list / str，用于日志与指标。"""
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, list):
        return [redact_deep(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_deep(item) for item in value)
    if isinstance(value, dict):
        return {key: redact_deep(item) for key, item in value.items()}
    return value
