from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, reindex  # noqa: E402


def main() -> int:
    db.init_db()
    with db.get_db() as conn:
        counts = reindex.reindex(conn)
    print(f"reindexed: cases={counts['cases']} doc_chunks={counts['doc_chunks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
