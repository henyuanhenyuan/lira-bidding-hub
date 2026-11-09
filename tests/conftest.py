import os
import tempfile

os.environ.setdefault("LIRA_DATA_DIR", tempfile.mkdtemp(prefix="lira-test-"))
os.environ["LIRA_LLM"] = "off"
os.environ["LIRA_SCHEDULER"] = "off"
os.environ["LIRA_CELERY_EAGER"] = "1"
os.environ["LIRA_AUTH"] = "off"



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
    "model_call",
    "job_run",
    "app_user",
    "approval_log",
    "agent_step",
    "agent_run",
    "execution",
    "eval_run",
    "eval_badcase",
    "judge_cache",
    "agent_memory",
    "span",
    "doc_chunk",
    "doc",
    "skill",
    "eval_case",
    "case",
    "collect_task",
    "collect_log",
    "manual_review",
]

CONFIG_KEYS = (
    "LLM_BACKEND", "LLM_ROUTE", "OLLAMA_MODEL", "OLLAMA_URL",
    "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "LLM_ENABLED",
)


@pytest.fixture(autouse=True)
def _restore_config():
    from app import config as app_config

    snapshot = {key: getattr(app_config, key) for key in CONFIG_KEYS}
    yield
    for key, value in snapshot.items():
        setattr(app_config, key, value)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    db.init_db()


@pytest.fixture(autouse=True)
def clean_db(_schema):
    joined = ", ".join(f'"{t}"' for t in TABLES)
    with db.get_db() as conn:
        conn.execute(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE")
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = 'public' AND table_name LIKE 'vec\\_%'"
        ).fetchall()
        if rows:
            vectors = ", ".join(f'"{row["table_name"]}"' for row in rows)
            conn.execute(f"TRUNCATE TABLE {vectors}")
    yield
