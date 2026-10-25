from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.getenv("LIRA_REDIS_URL", "redis://127.0.0.1:6379/0")
EAGER = os.getenv("LIRA_CELERY_EAGER", "0").lower() in {"1", "true", "on"}

celery_app = Celery(
    "lira",
    broker=BROKER_URL,
    backend=BROKER_URL,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_always_eager=EAGER,
    task_eager_propagates=True,
    task_store_eager_result=False,
    timezone=os.getenv("LIRA_TZ", "Asia/Shanghai"),
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)


def _hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def _beat_schedule() -> dict:
    from . import scheduler

    schedule = {
        f"lira.job.{kind}": {"task": f"lira.job.{kind}", "schedule": float(interval)}
        for kind, (interval, _fn) in scheduler.JOBS.items()
    }
    digest_h, digest_m = _hhmm(scheduler.DIGEST_AT)
    schedule["lira.job.digest"] = {
        "task": "lira.job.digest",
        "schedule": crontab(hour=digest_h, minute=digest_m),
    }
    backup_h, backup_m = _hhmm(scheduler.config.BACKUP_AT)
    schedule["lira.job.backup"] = {
        "task": "lira.job.backup",
        "schedule": crontab(hour=backup_h, minute=backup_m),
    }
    schedule["lira.job.collect_dispatch"] = {
        "task": "lira.job.collect_dispatch",
        "schedule": float(os.getenv("LIRA_COLLECT_INTERVAL", "15")),
    }
    return schedule


celery_app.conf.beat_schedule = _beat_schedule()
