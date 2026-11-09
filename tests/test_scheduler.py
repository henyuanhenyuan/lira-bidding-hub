import pytest

from app import db, scheduler


def test_unknown_job_raises():
    with pytest.raises(KeyError):
        scheduler.run_now("nope")


def test_run_now_records_job_run():
    scheduler.run_now("backup")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM job_run WHERE kind = 'backup' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok", row["detail"]


def test_backup_due_once_per_day(monkeypatch):
    monkeypatch.setattr(scheduler.config, "BACKUP_AT", "00:00")
    monkeypatch.setattr(scheduler, "_daily", {})
    assert scheduler._backup_due() is True
    assert scheduler._backup_due() is False


def test_backup_job_writes_file(monkeypatch):
    detail = scheduler.job_backup()
    assert "lira-" in detail
    with db.get_db() as conn:
        pass
    from app import config
    assert list((config.DATA_DIR / "backups").glob("lira-*.sql"))


def test_state_shape():
    st = scheduler.state()
    assert set(st) >= {"enabled", "last", "recent"}
    assert isinstance(st["recent"], list)
