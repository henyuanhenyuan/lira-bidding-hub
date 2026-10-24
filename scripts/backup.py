"""在线备份 + inbox 归档（SQLite 或 PostgreSQL）。

用法：
    python scripts/backup.py            # 备份到 data/backups/
    python scripts/backup.py D:\\backup  # 指定目录
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import backup  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = backup.run(target_dir=target)
    print(f"backup written: {result['path']} ({result['size_kb']} KB)")


if __name__ == "__main__":
    main()
