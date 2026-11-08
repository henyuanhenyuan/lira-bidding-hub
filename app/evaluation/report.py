"""把一次评测运行渲染成 Markdown，便于贴进 PR 与归档。"""

from __future__ import annotations

from typing import Any

COLUMNS = (
    ("total", "用例数"),
    ("passed", "通过"),
    ("action_accuracy", "动作准确率"),
    ("evidence_closure_rate", "证据闭包率"),
    ("trace_completion_rate", "轨迹完整率"),
    ("avg_latency_ms", "平均耗时(ms)"),
)


def _pct(value: Any) -> str:
    return f"{value:.1%}" if isinstance(value, float) else str(value)


def render(run: dict[str, Any]) -> str:
    summary = run.get("metrics") or {}
    lines = [
        f"# 评测报告 {run.get('run_key', '')}",
        "",
        f"- tier：`{run.get('tier')}`",
        f"- 通过：{summary.get('passed', 0)} / {summary.get('total', 0)}",
        "",
        "## 总指标",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
    ]
    for key, label in COLUMNS:
        value = summary.get(key)
        if isinstance(value, float) and key != "avg_latency_ms":
            value = _pct(value)
        lines.append(f"| {label} | {value} |")

    for slice_key, title in (("by_segment", "分场景"), ("by_difficulty", "分难度")):
        buckets = summary.get(slice_key) or {}
        if not buckets:
            continue
        lines += ["", f"## {title}", "", "| 分组 | 用例 | 通过 | 动作准确率 |", "| --- | --- | --- | --- |"]
        for name, item in buckets.items():
            lines.append(
                f"| {name} | {item['total']} | {item['passed']} | "
                f"{_pct(item['action_accuracy'])} |"
            )

    failures = [item for item in run.get("results", []) if not item.get("passed")]
    if failures:
        lines += ["", "## 坏例", "", "| 用例 | 场景 | 期望 → 实际 |", "| --- | --- | --- |"]
        for item in failures[:20]:
            lines.append(
                f"| {item.get('case')} | {item.get('segment')} | "
                f"{item.get('expected_action')} → {item.get('actual_action')} |"
            )
        if len(failures) > 20:
            lines.append(f"| … 其余 {len(failures) - 20} 条 | | |")
    return "\n".join(lines) + "\n"
