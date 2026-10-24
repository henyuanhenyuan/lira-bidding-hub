from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceTier = Literal[0, 1, 2, 3, 4]
Severity = Literal["L1", "L2", "L3"]
GateLevel = Literal["strong", "confirm", "observe"]


class Coupon(BaseModel):
    kind: str = "shop"
    threshold: float | None = None
    discount: float | None = None
    text: str | None = None
    stackable: bool = False


class Promotion(BaseModel):
    kind: str = "cross_store"
    threshold: float | None = None
    discount: float | None = None
    text: str | None = None


class Coin(BaseModel):
    rate: float = 0.0
    cap: float = 0.0


class Observation(BaseModel):
    """只收原始观测，绝不收到手价。"""

    list_price: float | None = None
    coupons: list[Coupon] | None = None
    promotions: list[Promotion] | None = None
    coin: Coin | None = None
    member_price: float | None = None
    live_price: float | None = None
    quantity: int = 1
    region: str | None = None
    account_tier: str = "normal"
    title: str | None = None
    main_image_url: str | None = None
    stock_signal: str | None = None

    @field_validator("list_price", "member_price", "live_price")
    @classmethod
    def _positive_or_none(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("price must be non-negative")
        return v


class SnapshotIn(BaseModel):
    target_id: str
    ts: str
    collector: str = "manual"
    source_tier: SourceTier = 4
    observation: Observation
    screenshot_ref: str | None = None
    backfill: bool = False


class IngestBatch(BaseModel):
    snapshots: list[SnapshotIn]
    file_name: str | None = None


class PricePoint(BaseModel):
    target_id: str
    ts: str
    point: float
    price_low: float
    price_high: float
    confidence: float
    missing_fields: list[str]


class EventOut(BaseModel):
    id: str
    target_id: str
    ts: str
    type: str
    severity: Severity
    gate_level: GateLevel
    suppressed: bool
    note: str | None
    evidence: list[str]
    rule_version: str


class SuggestionOut(BaseModel):
    id: str
    event_id: str
    action: str
    impact_low: float | None
    impact_high: float | None
    confidence: float
    gate_level: GateLevel
    narrative: str
    generated_by: str
    status: str
    created_at: str


class EvidenceCheck(BaseModel):
    ok: bool
    valid: list[str]
    invalid: list[str]
