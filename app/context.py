"""上下文构建器：分层、按优先级裁剪、统一标记不可信内容。

层次（数字越小越重要）：
    L0 指令与约束（system，不裁剪）
    L1 事实与允许证据（必须保留）
    L2 案例与记忆（可截断）
    L3 规则文档（不可信，可截断或整段丢弃）

所有外部内容经 `wrap_untrusted` 标记后再进入上下文，模型侧只看到数据。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .llm.counting import estimate_tokens, truncate_to_budget
from .safety.injection import wrap_untrusted

PRIORITY_SYSTEM = 0
PRIORITY_FACTS = 1
PRIORITY_MEMORY = 2
PRIORITY_RULES = 3


@dataclass
class Section:
    name: str
    text: str
    priority: int
    taint: bool = False
    source: str = ""

    def rendered(self) -> str:
        if self.taint:
            return wrap_untrusted(self.text, source=self.source or self.name)
        return self.text


@dataclass
class Context:
    max_tokens: int
    sections: list[Section] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)
    kept: dict[str, str] = field(default_factory=dict)

    def add(
        self, name: str, text: str, priority: int,
        taint: bool = False, source: str = "",
    ) -> None:
        if text:
            self.sections.append(
                Section(name, str(text), priority, taint=taint, source=source)
            )

    def _ordered(self) -> list[Section]:
        return sorted(self.sections, key=lambda item: item.priority)

    def render(self) -> str:
        """按优先级拼装；超预算时先丢低优先级、再截断次低优先级。"""
        self.dropped.clear()
        self.truncated.clear()
        self.kept.clear()
        kept: list[Section] = []
        used = 0
        for section in self._ordered():
            text = section.rendered()
            cost = estimate_tokens(text)
            if used + cost <= self.max_tokens:
                kept.append(Section(section.name, text, section.priority))
                self.kept[section.name] = text
                used += cost
                continue
            remaining = self.max_tokens - used
            if remaining > 40 and section.priority <= PRIORITY_FACTS:
                text = truncate_to_budget(text, remaining)
                kept.append(Section(section.name, text, section.priority))
                self.kept[section.name] = text
                self.truncated.append(section.name)
                used += estimate_tokens(text)
            else:
                self.dropped.append(section.name)
        return "\n\n".join(item.text for item in kept)

    def stats(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "sections": len(self.sections),
            "dropped": list(self.dropped),
            "truncated": list(self.truncated),
        }


def build_analysis_payload(
    facts: dict[str, Any],
    allowed: set[str],
    max_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """构造归因请求的 facts 载荷，并把上下文裁剪结果带回给调用方。"""
    rules = list(facts.get("rules") or [])
    memory_notes = str(facts.get("memory_notes") or "")

    context = Context(max_tokens=max_tokens)
    context.add(
        "facts",
        json.dumps(
            {key: value for key, value in facts.items()
             if key not in {"rules", "memory_notes"}},
            ensure_ascii=False,
        ),
        PRIORITY_FACTS,
    )
    context.add(
        "allowed_evidence",
        json.dumps(sorted(allowed), ensure_ascii=False),
        PRIORITY_FACTS,
    )
    context.add("memory", memory_notes, PRIORITY_MEMORY)
    for index, rule in enumerate(rules):
        content = str(rule.get("content") or "")
        context.add(
            f"rule:{rule.get('id') or index}", content,
            PRIORITY_RULES, taint=True,
            source=str(rule.get("id") or f"rule:{index}"),
        )

    context.render()
    kept_rules = []
    for index, rule in enumerate(rules):
        name = f"rule:{rule.get('id') or index}"
        if name in context.kept:
            kept_rules.append({**rule, "content": context.kept[name]})

    payload = {
        "facts": {
            key: value for key, value in facts.items()
            if key not in {"rules", "memory_notes"}
        },
        "allowed_evidence_ids": sorted(allowed),
    }
    if kept_rules:
        payload["facts"]["rules"] = kept_rules
    if "memory" in context.kept:
        payload["facts"]["memory_notes"] = context.kept["memory"]
    return payload, context.stats()
