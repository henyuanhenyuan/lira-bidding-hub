"""SQLite → PostgreSQL 数据搬迁。

用法：
    set LIRA_DATABASE_URL=postgresql://lira:lira@127.0.0.1:5432/lira
    python scripts/migrate_sqlite_to_pg.py
    python scripts/migrate_sqlite_to_pg.py --sqlite data/lira.db --truncate
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(ROOT / "data" / "lira.db"))
    parser.add_argument("--truncate", action="store_true", help="先清空目标库")
    parser.add_argument("--database-url", default=os.getenv("LIRA_DATABASE_URL", ""))
    args = parser.parse_args()

    if not args.database_url:
        sys.exit("请设置 LIRA_DATABASE_URL 或传 --database-url")
    if not Path(args.sqlite).exists():
        sys.exit(f"找不到 SQLite 文件：{args.sqlite}")

    os.environ["LIRA_DATABASE_URL"] = args.database_url

    from app import migrate  # noqa: E402

    report = migrate.migrate(args.sqlite, truncate=args.truncate)
    print(f"{'table':<18}{'source':>8}{'target':>8}  status")
    mismatched = 0
    for table, row in report.items():
        flag = "ok"
        if row.get("missing"):
            flag = "missing in sqlite"
        elif row["target"] < row["source"]:
            flag = "target has fewer rows"
            mismatched += 1
        print(f"{table:<18}{row['source']:>8}{row['target']:>8}  {flag}")
    if mismatched:
        sys.exit(f"{mismatched} tables did not fully migrate")
    print("migration complete")


if __name__ == "__main__":
    main()
