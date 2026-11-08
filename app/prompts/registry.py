"""轻量 Prompt 注册表：集中管理文本与版本号，供网关与评测聚合使用。

文本仍以代码常量为准（避免两处维护漂移），注册表负责版本、命名与 schema 绑定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VERSIONS = {
    "analysis": "analysis-v1",
    "critic": "critic-v1",
    "judge": "judge-v1",
}


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    text: str
    schema: dict[str, Any] | None = None


def get(name: str) -> PromptSpec:
    from .. import agent

    if name == "analysis":
        return PromptSpec(name, VERSIONS[name], agent.PROMPT, agent.OUTPUT_SCHEMA)
    if name == "critic":
        return PromptSpec(name, VERSIONS[name], agent.CRITIC_PROMPT, agent.CRITIC_SCHEMA)
    raise KeyError(f"未知 prompt：{name}")


def version_of(name: str) -> str:
    return VERSIONS.get(name, "unknown")
