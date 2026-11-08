import os
import tempfile

os.environ.setdefault("LIRA_DATA_DIR", tempfile.mkdtemp(prefix="lira-test-"))
os.environ["LIRA_LLM"] = "off"
os.environ["LIRA_SCHEDULER"] = "off"
os.environ["LIRA_CELERY_EAGER"] = "1"
os.environ["LIRA_AUTH"] = "off"

TEST_BACKEND = os.getenv("LIRA_TEST_DB", "sqlite")


def _ensure_database(url: str) -> None:
    from urllib.parse import urlsplit, urlunsplit

    import psycopg

    parts = urlsplit(url)
    name = parts.path.lstrip("/") or "postgres"
    if not name.replace("_", "").isalnum():
        raise RuntimeError(f"非法数据库名：{name}")
    admin = urlunsplit(
        (parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment)
    )
    try:
        with psycopg.connect(admin, autocommit=True) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{name}"')
    except psycopg.Error as exc:
        raise RuntimeError(f"PostgreSQL 不可用（{parts.netloc}）：{exc}") from exc


if TEST_BACKEND == "postgres":
    os.environ["LIRA_DATABASE_URL"] = os.getenv(
        "LIRA_TEST_DATABASE_URL",
        "postgresql://lira:lira@127.0.0.1:5432/lira_test",
    )
    _ensure_database(os.environ["LIRA_DATABASE_URL"])

import pytest  # noqa: E402

from app import db  # noqa: E402

TABLES = [
    "action_log",
    "outcome",
    "suggestion",
    "event",
    "price_point",
    "snapshot",
    "mapping",
    "my_product",
    "target",
    "ingest_log",
    "inbox_file",
    "model_call",
    "job_run",
    "app_user",
    "approval_log",
    "review_insight",
    "review",
    "agent_step",
    "agent_run",
    "execution",
    "eval_run",
    "eval_badcase",
    "judge_cache",
    "agent_memory",
    "span",
    "outcome_reminder",
    "doc_chunk",
    "doc",
    "skill",
    "eval_case",
    "case_fts",
    "case",
    "collect_task",
    "collect_log",
    "manual_review",
]

if TEST_BACKEND == "postgres":
    TABLES = [t for t in TABLES if t != "case_fts"]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    db.init_db()


@pytest.fixture(autouse=True)
def clean_db(_schema):
    if db.BACKEND == "postgres":
        joined = ", ".join(f'"{t}"' for t in TABLES)
        with db.get_db() as conn:
            conn.execute(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE")
    else:
        with db.get_db() as conn:
            for t in TABLES:
                conn.execute(f'DELETE FROM "{t}"')
    yield
