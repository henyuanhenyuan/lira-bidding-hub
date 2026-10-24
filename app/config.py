from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("LIRA_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "lira.db"
DATABASE_URL = os.getenv("LIRA_DATABASE_URL", "")
WEB_DIR = BASE_DIR / "web"
NEXT_DIR = BASE_DIR / "web-next" / "dist"

# 本地模型（可选）。不可用时全部走确定性模板。
OLLAMA_URL = os.getenv("LIRA_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("LIRA_OLLAMA_MODEL", "qwen3:4b")
LLM_TIMEOUT_S = float(os.getenv("LIRA_LLM_TIMEOUT", "20"))
LLM_ENABLED = os.getenv("LIRA_LLM", "auto")  # auto | off | on

# 采集与告警阈值
PRICE_DELTA_ALERT = 0.03          # 3% 触发价格事件
PRICE_DELTA_L2 = 0.10
PRICE_DELTA_L3 = 0.20
BAND_BREACH_RATIO = 0.95          # 竞品低于我方价 5% 视为击穿

# L3 只允许这两级数据源触发
L3_ALLOWED_TIERS = (0, 1)

# 运维节奏
BACKUP_AT = os.getenv("LIRA_BACKUP_AT", "03:30")
BACKUP_KEEP = int(os.getenv("LIRA_BACKUP_KEEP", "7"))
CONNECTOR_INTERVAL = float(os.getenv("LIRA_CONNECTOR_INTERVAL", "1800"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "inbox").mkdir(parents=True, exist_ok=True)
