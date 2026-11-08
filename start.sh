#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m pip install --quiet -r requirements.txt
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${LIRA_PORT:-8011}"
