from __future__ import annotations

import csv
import io
import json
from typing import Any

from .contracts import SnapshotIn


def _opt_float(v: str | None) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    return float(v)


def _json_cell(v: str | None) -> Any:
    if v is None or str(v).strip() == "":
        return None
    return json.loads(v)


def parse_csv_bytes(raw: bytes) -> tuple[list[SnapshotIn], list[dict[str, Any]]]:
    """空单元格一律视为未知，绝不当作 0。"""
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    snaps: list[SnapshotIn] = []
    errors: list[dict[str, Any]] = []

    for idx, r in enumerate(rows, start=2):
        try:
            coin_rate = _opt_float(r.get("coin_rate"))
            coin = (
                {"rate": coin_rate, "cap": _opt_float(r.get("coin_cap")) or 0.0}
                if coin_rate is not None
                else None
            )
            snaps.append(
                SnapshotIn(
                    target_id=r["target_id"],
                    ts=r["ts"],
                    collector=r.get("collector") or "csv-import",
                    source_tier=int(r.get("source_tier") or 4),
                    observation={
                        "list_price": _opt_float(r.get("list_price")),
                        "coupons": _json_cell(r.get("coupons")),
                        "promotions": _json_cell(r.get("promotions")),
                        "coin": coin,
                        "member_price": _opt_float(r.get("member_price")),
                        "live_price": _opt_float(r.get("live_price")),
                        "account_tier": r.get("account_tier") or "normal",
                        "title": r.get("title") or None,
                    },
                )
            )
        except Exception as exc:
            errors.append({"line": idx, "error": str(exc)})

    return snaps, errors
