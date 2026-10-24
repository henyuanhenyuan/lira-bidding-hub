from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .contracts import GateLevel, PricePoint

RULE_VERSION = "rules-v1"


@dataclass
class DetectedEvent:
    type: str
    severity: str
    gate_level: GateLevel
    note: str
    evidence: list[str] = field(default_factory=list)
    suppressed: bool = False


def _gate(confidence: float, severity: str) -> GateLevel:
    if confidence >= 0.70 and severity in ("L2", "L3"):
        return "strong"
    if confidence >= 0.50:
        return "confirm"
    return "observe"


def _severity_from_delta(delta: float) -> str:
    a = abs(delta)
    if a >= config.PRICE_DELTA_L3:
        return "L3"
    if a >= config.PRICE_DELTA_L2:
        return "L2"
    return "L1"


def _apply_tier_policy(severity: str, source_tier: int) -> tuple[str, str | None]:
    """L3 只允许官方/三方数据触发，其余降级为 L2。"""
    if severity == "L3" and source_tier not in config.L3_ALLOWED_TIERS:
        return "L2", "downgraded_by_tier"
    return severity, None


def detect(
    *,
    target_id: str,
    snapshot_id: str,
    ts: str,
    source_tier: int,
    point: PricePoint,
    prev: PricePoint | None,
    my_price: float | None,
    discontinuity: bool = False,
) -> list[DetectedEvent]:
    events: list[DetectedEvent] = []
    base_evidence = [f"snap:{snapshot_id}", f"pp:{target_id}:{ts}"]

    if discontinuity:
        return [
            DetectedEvent(
                type="source_switch",
                severity="L1",
                gate_level="observe",
                note="采集源变更，本窗口抑制差值告警",
                evidence=base_evidence,
                suppressed=True,
            )
        ]

    cur_mid = (point.price_low + point.price_high) / 2
    prev_mid = (prev.price_low + prev.price_high) / 2 if prev else None

    if prev_mid and prev_mid > 0:
        delta = (cur_mid - prev_mid) / prev_mid
        if abs(delta) >= config.PRICE_DELTA_ALERT:
            etype = "price_drop" if delta < 0 else "price_rise"
            sev, tier_note = _apply_tier_policy(
                _severity_from_delta(delta), source_tier
            )
            gate = _gate(point.confidence, sev)
            note = f"到手价估算 {cur_mid:.2f}，较上次 {delta:+.1%}"
            if tier_note:
                note += f"（{tier_note}）"
            events.append(
                DetectedEvent(
                    type=etype,
                    severity=sev,
                    gate_level=gate,
                    note=note,
                    evidence=base_evidence + [f"pp:{target_id}:{prev.ts}"],
                )
            )

    if my_price and cur_mid < my_price * config.BAND_BREACH_RATIO:
        sev, tier_note = _apply_tier_policy("L3", source_tier)
        gate = _gate(point.confidence, sev)
        note = f"竞品到手价击穿我方价格带（我方 {my_price:.2f}）"
        if tier_note:
            note += f"（{tier_note}）"
        if not any(e.type == "band_breach" for e in events):
            events.append(
                DetectedEvent(
                    type="band_breach",
                    severity=sev,
                    gate_level=gate,
                    note=note,
                    evidence=base_evidence,
                )
            )

    return events
