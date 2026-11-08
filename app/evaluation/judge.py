"""LLM-as-judge：固定模型 + 版本化 rubric + 判定缓存。

P5 只提供框架与校准；真实模型接入在 P6 的网关里完成。
未配置 `LIRA_JUDGE_MODEL` 时 `build_default()` 返回 None，评测退回确定性代理。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import db

RUBRIC_VERSION = "faithfulness-v1"
CALIBRATION_PATH = Path(__file__).with_name("baselines") / "judge_calibration.json"

RUBRIC = """你是严格的评测员。给定【问题】【检索上下文】【回答】，按 1-5 分打分：
- faithfulness：回答中的每个事实是否都能在检索上下文中找到依据；编造即为 1 分。
- relevance：回答是否直接解决了问题；答非所问为 1 分。
只输出 JSON：{"faithfulness": <1-5>, "relevance": <1-5>, "rationale": "<80字内>"}
"""


@dataclass(frozen=True)
class JudgeVerdict:
    faithfulness: float
    relevance: float
    rationale: str

    @property
    def label(self) -> str:
        return "pass" if self.faithfulness >= 4 and self.relevance >= 4 else "fail"


def _cache_key(model: str, rubric_version: str, question: str,
               contexts: list[str], answer: str) -> str:
    blob = json.dumps(
        {"model": model, "rubric": rubric_version, "q": question,
         "c": contexts, "a": answer},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Judge:
    """传入 ask(prompt) -> str 的调用器即可工作；结果按内容哈希缓存。"""

    def __init__(
        self,
        ask: Callable[[str], str],
        model: str,
        rubric_version: str = RUBRIC_VERSION,
    ) -> None:
        self._ask = ask
        self.model = model
        self.rubric_version = rubric_version

    def evaluate(
        self, question: str, contexts: list[str], answer: str
    ) -> JudgeVerdict | None:
        key = _cache_key(self.model, self.rubric_version, question, contexts, answer)
        cached = self._load(key)
        if cached:
            return cached
        prompt = (
            RUBRIC
            + "\n【问题】\n" + question
            + "\n【检索上下文】\n" + "\n---\n".join(contexts)
            + "\n【回答】\n" + answer
        )
        try:
            raw = self._ask(prompt)
            data = _extract_json(raw)
            verdict = JudgeVerdict(
                faithfulness=float(data["faithfulness"]),
                relevance=float(data["relevance"]),
                rationale=str(data.get("rationale", ""))[:300],
            )
        except (KeyError, TypeError, ValueError):
            return None
        self._store(key, verdict)
        return verdict

    def _load(self, key: str) -> JudgeVerdict | None:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT payload FROM judge_cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        return JudgeVerdict(
            faithfulness=data["faithfulness"],
            relevance=data["relevance"],
            rationale=data.get("rationale", ""),
        )

    def _store(self, key: str, verdict: JudgeVerdict) -> None:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO judge_cache (key, model, rubric_version, verdict,"
                " payload, created_at) VALUES (?,?,?,?,?,?)",
                (
                    key, self.model, self.rubric_version, verdict.label,
                    json.dumps(
                        {
                            "faithfulness": verdict.faithfulness,
                            "relevance": verdict.relevance,
                            "rationale": verdict.rationale,
                        },
                        ensure_ascii=False,
                    ),
                    db.now_iso(),
                ),
            )


def _extract_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("judge 未返回 JSON")
    return json.loads(text[start:end + 1])


def load_calibration(path: Path | None = None) -> dict[str, Any] | None:
    target = path or CALIBRATION_PATH
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except ValueError:
        return None


def is_calibrated(
    min_kappa: float = 0.70, path: Path | None = None
) -> bool:
    report = load_calibration(path)
    if not report:
        return False
    return bool(report.get("passed")) and float(report.get("cohen_kappa") or 0) >= min_kappa


def build_default() -> Judge | None:
    """未显式配置判官模型时返回 None（调分包在 P6 接入）。"""
    model = os.getenv("LIRA_JUDGE_MODEL", "").strip()
    if not model:
        return None
    ask = _load_ask_callable()
    if ask is None:
        return None
    return Judge(ask=ask, model=model)


def _load_ask_callable() -> Callable[[str], str] | None:
    from .. import agent  # 延迟导入，避免评测包对 Agent 的循环依赖

    def ask(prompt: str) -> str:
        payload = agent._post_chat(
            {
                "model": os.getenv("LIRA_JUDGE_MODEL", ""),
                "stream": False,
                "think": False,
                "options": {"temperature": 0.0, "num_predict": 200},
                "messages": [
                    {"role": "system", "content": RUBRIC},
                    {"role": "user", "content": prompt},
                ],
            }
        )
        return payload.get("message", {}).get("content") or ""

    return ask
