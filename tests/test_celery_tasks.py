from app import db, scheduler


def test_celery_app_uses_redis_and_eager_in_tests():
    from app.celery_app import celery_app

    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.broker_url.startswith("redis://")


def test_beat_schedule_covers_every_job():
    from app.celery_app import celery_app

    scheduled = set(celery_app.conf.beat_schedule)
    expected = {f"lira.job.{kind}" for kind in scheduler.JOBS}
    expected |= {"lira.job.digest", "lira.job.backup"}
    assert expected <= scheduled


def test_celery_task_records_job_run():
    from app.tasks import task_outcome_review

    result = task_outcome_review.apply().get()
    assert result.endswith(" ok"), result
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM job_run WHERE kind = 'outcome_review' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok", row["detail"]


def test_run_now_supports_backup():
    assert scheduler.run_now("backup")
