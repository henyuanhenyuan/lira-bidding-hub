"""演示数据补充：给目标分配地区与策略，给商品补成本价。

只对缺省数据生效，不覆盖已有配置。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

REGIONS = ["杭州", "上海", "成都", "深圳", "北京"]
STRATEGIES = ["follow", "undercut", "follow", "match_band"]


def main() -> None:
    with db.get_db() as conn:
        targets = conn.execute(
            "SELECT id, region, pricing_strategy FROM target ORDER BY title"
        ).fetchall()
        for index, row in enumerate(targets):
            region = REGIONS[index % len(REGIONS)]
            strategy = STRATEGIES[index % len(STRATEGIES)]
            conn.execute(
                "UPDATE target SET region = ?, pricing_strategy = ? WHERE id = ?",
                (region, strategy, row["id"]),
            )
        products = conn.execute(
            "SELECT sku, price, cost, margin_floor FROM my_product"
        ).fetchall()
        filled = 0
        for row in products:
            if row["cost"] is None and row["price"]:
                conn.execute(
                    "UPDATE my_product SET cost = ?, margin_floor = COALESCE(margin_floor, 0.15)"
                    " WHERE sku = ?",
                    (round(float(row["price"]) * 0.62, 2), row["sku"]),
                )
                filled += 1
    print(f"targets={len(targets)} regions={len(REGIONS)} costs_filled={filled}")


if __name__ == "__main__":
    main()
