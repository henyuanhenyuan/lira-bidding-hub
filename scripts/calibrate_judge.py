"""判官校准：用人工标注样本算 Cohen's kappa，低于阈值拒绝启用。

用法：
  export LIRA_JUDGE_MODEL=qwen-plus          # 或本地 ollama 模型
  python scripts/calibrate_judge.py --labels app/evaluation/golden/judge_calibration.jsonl
退出码：0 通过；1 kappa 不达标；2 未配置判官模型。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.evaluation import judge as judge_mod  # noqa: E402
from app.evaluation import metrics  # noqa: E402

DEFAULT_LABELS = ROOT / "app" / "evaluation" / "golden" / "judge_calibration.jsonl"
DEFAULT_OUT = ROOT / "app" / "evaluation" / "baselines" / "judge_calibration.json"


def load_labels(path: Path) -> list[dict]:
    items = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                items.append(json.loads(text))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="判官校准")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--min-kappa", type=float, default=0.70)
    args = parser.parse_args()

    db.init_db()
    judge = judge_mod.build_default()
    if judge is None:
        print("未配置 LIRA_JUDGE_MODEL 或模型不可用，无法校准。")
        return 2

    labels = load_labels(args.labels)
    human: list[str] = []
    predicted: list[str] = []
    rows = []
    for item in labels:
        verdict = judge.evaluate(item["question"], item["contexts"], item["answer"])
        if verdict is None:
            rows.append({**item, "judge_label": None})
            continue
        human.append(item["human_label"])
        predicted.append(verdict.label)
        rows.append(
            {
                **item, "judge_label": verdict.label,
                "faithfulness": verdict.faithfulness,
                "relevance": verdict.relevance,
            }
        )

    kappa = metrics.cohen_kappa(human, predicted)
    report = {
        "model": judge.model,
        "rubric_version": judge.rubric_version,
        "samples": len(labels),
        "scored": len(human),
        "cohen_kappa": kappa,
        "min_kappa": args.min_kappa,
        "passed": kappa >= args.min_kappa,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"样本 {report['scored']}/{report['samples']}，kappa={kappa}，阈值={args.min_kappa}")
    print("通过" if report["passed"] else "未通过：判官不得用于门禁")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
