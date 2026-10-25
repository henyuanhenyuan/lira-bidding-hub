from __future__ import annotations

from celery import shared_task

from . import scheduler


@shared_task(name="lira.job.inbox_scan")
def task_inbox_scan() -> str:
    return scheduler.run_now("inbox_scan")


@shared_task(name="lira.job.mapping_suggest")
def task_mapping_suggest() -> str:
    return scheduler.run_now("mapping_suggest")


@shared_task(name="lira.job.outcome_review")
def task_outcome_review() -> str:
    return scheduler.run_now("outcome_review")


@shared_task(name="lira.job.review_insight")
def task_review_insight() -> str:
    return scheduler.run_now("review_insight")


@shared_task(name="lira.job.connector_sync")
def task_connector_sync() -> str:
    return scheduler.run_now("connector_sync")


@shared_task(name="lira.job.digest")
def task_digest() -> str:
    return scheduler.run_now("digest")


@shared_task(name="lira.job.backup")
def task_backup() -> str:
    return scheduler.run_now("backup")
