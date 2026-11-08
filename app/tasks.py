from __future__ import annotations

from celery import shared_task

from . import scheduler


@shared_task(name="lira.job.mapping_suggest")
def task_mapping_suggest() -> str:
    return scheduler.run_now("mapping_suggest")


@shared_task(name="lira.job.outcome_review")
def task_outcome_review() -> str:
    return scheduler.run_now("outcome_review")


@shared_task(name="lira.job.backup")
def task_backup() -> str:
    return scheduler.run_now("backup")


@shared_task(name="lira.job.collect_dispatch")
def task_collect_dispatch() -> dict:
    from . import collector

    out: dict = {"recovered": collector.recover_stale()}
    for channel in ("api", "manual"):
        try:
            out[channel] = collector.dispatch_due(channel)
        except Exception as exc:
            out[channel] = {"error": str(exc)}
    return out
