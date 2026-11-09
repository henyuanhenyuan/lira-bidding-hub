from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("LIRA_DATA_DIR", BASE_DIR / "data"))
DATABASE_URL = os.getenv(
    "LIRA_DATABASE_URL", "postgresql://lira:lira@127.0.0.1:5432/lira"
)
NEXT_DIR = BASE_DIR / "web-next" / "dist"

# 模型通道。legacy = 旧的直连 Ollama；gateway = 多 Provider 路由（推荐）。
# 本地 Ollama 适合开发与离线演示；对外演示/生产建议走 OpenAI 兼容通道（qwen-plus / DeepSeek）。
OLLAMA_URL = os.getenv("LIRA_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("LIRA_OLLAMA_MODEL", "qwen3:4b")
LLM_TIMEOUT_S = float(os.getenv("LIRA_LLM_TIMEOUT", "20"))
LLM_ENABLED = os.getenv("LIRA_LLM", "auto")  # auto | off | on

LLM_BACKEND = os.getenv("LIRA_LLM_BACKEND", "legacy")  # legacy | gateway
LLM_ROUTE = os.getenv("LIRA_LLM_ROUTE", "auto")        # auto | ollama | openai
OPENAI_BASE_URL = os.getenv("LIRA_OPENAI_BASE_URL", "")
OPENAI_API_KEY = os.getenv("LIRA_OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("LIRA_OPENAI_MODEL", "qwen-plus")
JUDGE_MODEL = os.getenv("LIRA_JUDGE_MODEL", "")
LLM_RPM = int(os.getenv("LIRA_LLM_RPM", "60"))
LLM_MAX_RETRIES = int(os.getenv("LIRA_LLM_MAX_RETRIES", "2"))
LLM_MAX_PROMPT_TOKENS = int(os.getenv("LIRA_LLM_MAX_PROMPT_TOKENS", "6000"))
AGENT_MAX_STEPS = int(os.getenv("LIRA_AGENT_MAX_STEPS", "6"))
AGENT_MAX_SECONDS = float(os.getenv("LIRA_AGENT_MAX_SECONDS", "90"))
TAINT_ENFORCE = os.getenv("LIRA_TAINT_ENFORCE", "on") == "on"

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
