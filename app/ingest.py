from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from . import db, events, pricing, semantic, stream
from .contracts import PricePoint, SnapshotIn


@dataclass
class IngestReport:
    rows_in: int = 0
    rows_ok: int = 0
    rows_dup: int = 0
    rows_rejected: int = 0
    events_created: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_in": self.rows_in,
            "rows_ok": self.rows_ok,
            "rows_dup": self.rows_dup,
            "rows_rejected": self.rows_rejected,
            "events_created": self.events_created,
            "errors": self.errors,
        }


def _content_hash(snap: SnapshotIn) -> str:
    payload = snap.observation.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_target(conn, snap: SnapshotIn) -> None:
    row = conn.execute("SELECT id, region FROM target WHERE id = ?", (snap.target_id,)).fetchone()
    region = snap.observation.region
    if row:
        # 地区是动态维度：采集端带来新地区时跟随更新，未带则保持原值
        if region and region != row["region"]:
            conn.execute(
                "UPDATE target SET region = ? WHERE id = ?", (region, snap.target_id)
            )
        return
    title = snap.observation.title or snap.target_id
    conn.execute(
        "INSERT INTO target (id, platform, external_id, title, my_sku, my_price,"
        " region, active) VALUES (?, 'taobao', ?, ?, NULL, NULL, ?, 1)",
        (snap.target_id, snap.target_id, title, region or "全国"),
    )


def _prev_price_point(conn, target_id: str, ts: str) -> PricePoint | None:
    row = conn.execute(
        "SELECT * FROM price_point WHERE target_id = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
        (target_id, ts),
    ).fetchone()
    if not row:
        return None
    return PricePoint(
        target_id=row["target_id"],
        ts=row["ts"],
        point=(row["price_low"] + row["price_high"]) / 2,
        price_low=row["price_low"],
        price_high=row["price_high"],
        confidence=row["confidence"],
        missing_fields=db.loads(row["missing_fields"], []),
    )


def _prev_snapshot(conn, target_id: str, ts: str):
    return conn.execute(
        "SELECT id, payload FROM snapshot WHERE target_id = ? AND ts < ?"
        " ORDER BY ts DESC LIMIT 1",
        (target_id, ts),
    ).fetchone()


def _last_collector(conn, target_id: str, ts: str) -> str | None:
    row = conn.execute(
        "SELECT collector FROM snapshot WHERE target_id = ? AND ts < ?"
        " ORDER BY ts DESC LIMIT 1",
        (target_id, ts),
    ).fetchone()
    return row["collector"] if row else None


def ingest(conn, batch_snaps: list[SnapshotIn], source: str = "api",
           file_name: str | None = None) -> IngestReport:
    report = IngestReport(rows_in=len(batch_snaps))

    for snap in batch_snaps:
        try:
            _ingest_one(conn, snap, report)
        except Exception as exc:  # 单行失败不影响整批
            report.rows_rejected += 1
            report.errors.append({"target_id": snap.target_id, "error": str(exc)})

    conn.execute(
        "INSERT INTO ingest_log (id, source, file_name, rows_in, rows_ok, rows_dup,"
        " rows_rejected, errors, received_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            db.new_id(), source, file_name, report.rows_in, report.rows_ok,
            report.rows_dup, report.rows_rejected,
            json.dumps(report.errors, ensure_ascii=False), db.now_iso(),
        ),
    )
    return report


def _ingest_one(conn, snap: SnapshotIn, report: IngestReport) -> None:
    _ensure_target(conn, snap)
    content_hash = _content_hash(snap)

    exists = conn.execute(
        "SELECT id FROM snapshot WHERE target_id=? AND ts=? AND collector=?"
        " AND content_hash=?",
        (snap.target_id, snap.ts, snap.collector, content_hash),
    ).fetchone()
    if exists:
        report.rows_dup += 1
        return

    point = pricing.compute(snap.target_id, snap.ts, snap.observation, snap.source_tier)
    if point is None:
        raise ValueError("list_price is required to compute 到手价")

    prev = _prev_price_point(conn, snap.target_id, snap.ts)
    prev_snap = _prev_snapshot(conn, snap.target_id, snap.ts)
    last_collector = _last_collector(conn, snap.target_id, snap.ts)
    discontinuity = last_collector is not None and last_collector != snap.collector

    snap_id = db.new_id()
    conn.execute(
        "INSERT INTO snapshot (id, target_id, ts, collector, source_tier, payload,"
        " content_hash, backfill, created_at, screenshot_ref)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            snap_id, snap.target_id, snap.ts, snap.collector, snap.source_tier,
            json.dumps(snap.observation.model_dump(mode="json"), ensure_ascii=False),
            content_hash, int(snap.backfill), db.now_iso(), snap.screenshot_ref,
        ),
    )

    conn.execute(
        "INSERT INTO price_point (target_id, ts, price_low, price_high,"
        " confidence, missing_fields, discontinuity) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT (target_id, ts) DO UPDATE SET"
        " price_low=excluded.price_low, price_high=excluded.price_high,"
        " confidence=excluded.confidence, missing_fields=excluded.missing_fields,"
        " discontinuity=excluded.discontinuity",
        (
            point.target_id, point.ts, point.price_low, point.price_high,
            point.confidence, json.dumps(point.missing_fields, ensure_ascii=False),
            int(discontinuity),
        ),
    )
    report.rows_ok += 1

    if snap.backfill:
        return

    target = conn.execute(
        "SELECT * FROM target WHERE id = ?", (snap.target_id,)
    ).fetchone()

    detected = events.detect(
        target_id=snap.target_id,
        snapshot_id=snap_id,
        ts=snap.ts,
        source_tier=snap.source_tier,
        point=point,
        prev=prev,
        my_price=target["my_price"] if target else None,
        discontinuity=discontinuity,
    )

    for ev in detected:
        event_id = db.new_id()
        conn.execute(
            "INSERT INTO event (id, target_id, ts, type, severity, gate_level,"
            " suppressed, note, evidence, rule_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id, snap.target_id, snap.ts, ev.type, ev.severity,
                ev.gate_level, int(ev.suppressed), ev.note,
                json.dumps(ev.evidence, ensure_ascii=False), events.RULE_VERSION,
            ),
        )
        report.events_created += 1
        stream.publish("event", {
            "id": event_id, "target_id": snap.target_id,
            "type": ev.type, "severity": ev.severity,
        })

    cur_obs = snap.observation.model_dump(mode="json")
    prev_obs = json.loads(prev_snap["payload"]) if prev_snap else None
    for ch in semantic.detect(prev_obs, cur_obs):
        conf = semantic.confidence_for_tier(snap.source_tier)
        gate = "strong" if conf >= 0.70 else "confirm"
        evidence = [f"snap:{prev_snap['id']}", f"snap:{snap_id}"]
        event_id = db.new_id()
        conn.execute(
            "INSERT INTO event (id, target_id, ts, type, severity, gate_level,"
            " suppressed, note, evidence, rule_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id, snap.target_id, snap.ts, f"{ch.field}_change",
                ch.severity, gate, 0, ch.note,
                json.dumps(evidence, ensure_ascii=False), semantic.RULE_VERSION,
            ),
        )
        report.events_created += 1
        stream.publish("event", {
            "id": event_id, "target_id": snap.target_id,
            "type": f"{ch.field}_change", "severity": ch.severity,
        })
