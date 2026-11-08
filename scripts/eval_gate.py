"""评测门禁：floor + delta 双门限；可生成/更新基线。

用法：
  python scripts/eval_gate.py --tier smoke
  python scripts/eval_gate.py --tier full --update-baseline
退出码 1 表示存在回归。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.evaluation import metrics as eval_metrics  # noqa: E402
from app.evaluation import report as eval_report  # noqa: E402
from app.evaluation import runner  # noqa: E402

DEFAULT_BASELINE = ROOT / "app" / "evaluation" / "baselines" / "baseline.json"
TRACKED = (
    "action_accuracy", "evidence_closure_rate", "trace_completion_rate",
)


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Lira 评测门禁")
    parser.add_argument("--tier", default="smoke", choices=["smoke", "core", "full"])
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-artifact", action="store_true")
    args = parser.parse_args()

    config = __import__("app.config", fromlist=["ensure_dirs"])
    config.ensure_dirs()
    db.init_db()

    run = runner.run(
        tier=args.tier,
        limit=args.limit or None,
        write_artifact=not args.no_artifact,
    )
    summary = {key: run["metrics"].get(key) for key in TRACKED}

    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(
                {"tier": args.tier, "metrics": summary,
                 "run_key": run["run_key"]},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"基线已更新：{args.baseline}")
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    baseline = load_baseline(args.baseline)
    base_metrics = baseline.get("metrics") or {}
    violations = eval_metrics.compare(summary, base_metrics)

    print(eval_report.render(run))
    if not baseline:
        print(f"未找到基线（{args.baseline}），本次仅报告不拦截。")
        return 0
    if violations:
        print("门禁未通过：")
        for item in violations:
            print(f"  - {item}")
        return 1
    print("门禁通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
