import pytest

from app import db, scheduler


def test_unknown_job_raises():
    with pytest.raises(KeyError):
        scheduler.run_now("nope")


def test_run_now_records_job_run():
    scheduler.run_now("inbox_scan")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM job_run WHERE kind = 'inbox_scan' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["status"] == "ok", row["detail"]


def test_digest_runs_at_most_once_per_day(monkeypatch):
    monkeypatch.setattr(scheduler, "DIGEST_AT", "00:00")
    monkeypatch.setattr(scheduler, "_daily", {})
    assert scheduler._digest_due() is True
    assert scheduler._digest_due() is False


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
    pattern = "lira-*.sql" if db.BACKEND == "postgres" else "lira-*.db"
    assert list((config.DATA_DIR / "backups").glob(pattern))


def test_connector_job_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(scheduler.connectors, "URL", "")
    assert scheduler.job_connector_sync() == "connector not configured"


def test_state_shape():
    st = scheduler.state()
    assert set(st) >= {"enabled", "last", "recent"}
    assert isinstance(st["recent"], list)
