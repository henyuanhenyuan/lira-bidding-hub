"""上传前本地校验：把 CSV 发给服务端干跑，不落库。

用法：
    python validate.py snapshots.csv --server http://127.0.0.1:8010
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--server", default="http://127.0.0.1:8010")
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"文件不存在：{args.csv}")
        return 2

    url = f"{args.server.rstrip('/')}/v1/import/validate"
    with args.csv.open("rb") as fh:
        r = httpx.post(url, files={"file": (args.csv.name, fh, "text/csv")}, timeout=30)

    if r.status_code != 200:
        print(f"服务返回 {r.status_code}: {r.text[:300]}")
        return 1

    data = r.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if data.get("ok"):
        print(f"\n校验通过，共 {data['rows']} 行，可以上传。")
        return 0
    print(f"\n发现 {len(data.get('errors', []))} 个问题，请修正后再上传。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
