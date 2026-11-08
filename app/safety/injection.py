"""Prompt 注入防御：不可信内容隔离 + 启发式检测 + 工具收窄。

原则：不依赖模型"自觉遵守"，而是在代码层把不可信内容标记出来，
一旦上下文里出现不可信来源，就只允许只读工具。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import config

UNTRUSTED_OPEN = '<untrusted source="{source}" taint="external">'
UNTRUSTED_CLOSE = "</untrusted>"

PATTERNS: tuple[tuple[str, str], ...] = (
    (r"忽略(以上|之前|上面|前面).{0,6}(指令|规则|要求)", "zh_ignore_instructions"),
    (r"(忽略|无视|绕过).{0,4}(规则|策略|护栏|限制)", "zh_bypass_rules"),
    (r"(系统提示|system\s*prompt|开发者消息)", "prompt_exfiltration"),
    (r"(你现在是|从现在起你是|扮演).{0,10}(无限制|管理员|裁判)", "role_override"),
    (r"(直接|必须)(输出|返回|给出).{0,8}(adjust_coupon|follow|hold|no_action)", "force_action"),
    (r"(已|已经)(审批|通过|授权)", "fake_approval"),
    (r"ignore\s+(all\s+)?(previous|above)\s+instructions", "en_ignore_instructions"),
    (r"override\s+(the\s+)?(policy|rules|system)", "en_override"),
    (r"(doc:|case:|snap:)(fake|nonexistent|任意)", "fake_evidence"),
    (r"(不要|禁止)(引用|校验).{0,6}证据", "skip_evidence"),
)

_COMPILED = tuple((re.compile(pattern, re.IGNORECASE), label) for pattern, label in PATTERNS)


@dataclass(frozen=True)
class InjectionFinding:
    score: float
    hits: tuple[str, ...] = field(default_factory=tuple)

    @property
    def suspicious(self) -> bool:
        return self.score >= 0.5


def scan(text: str) -> InjectionFinding:
    if not text:
        return InjectionFinding(0.0)
    hits = [label for regex, label in _COMPILED if regex.search(text)]
    score = min(1.0, 0.4 * len(hits))
    return InjectionFinding(score=round(score, 2), hits=tuple(hits))


def wrap_untrusted(text: str, source: str = "doc") -> str:
    """把外部内容包进隔离标记，并在内部中和伪角色前缀。"""
    safe_source = re.sub(r"[^A-Za-z0-9:._-]", "", source)[:80] or "doc"
    body = str(text or "")
    body = re.sub(r"(?im)^\s*(system|assistant|developer)\s*:", r"[\1]:", body)
    return UNTRUSTED_OPEN.format(source=safe_source) + body + UNTRUSTED_CLOSE


def restrict_tools(names: list[str], tainted: bool) -> list[str]:
    """上下文被污染时，只保留只读工具。"""
    from .. import tools

    if not tainted or not config.TAINT_ENFORCE:
        return list(names)
    return [name for name in names if not tools.is_write_tool(name)]


def is_tainted(sources: list[str] | None) -> bool:
    return bool(sources)
