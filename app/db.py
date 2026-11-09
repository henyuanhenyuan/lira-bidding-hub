from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DATABASE_URL

BACKEND = "postgres"

SCHEMA = """
CREATE TABLE IF NOT EXISTS target (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL DEFAULT 'taobao',
  external_id TEXT,
  title TEXT NOT NULL,
  my_sku TEXT,
  my_price REAL,
  region TEXT NOT NULL DEFAULT '全国',
  pricing_strategy TEXT NOT NULL DEFAULT 'follow',
  url TEXT,
  price_selector TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS snapshot (
  id TEXT PRIMARY KEY,
  target_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  collector TEXT NOT NULL,
  source_tier INTEGER NOT NULL,
  payload TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  backfill INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_snapshot_dedup
  ON snapshot(target_id, ts, collector, content_hash);
CREATE INDEX IF NOT EXISTS ix_snapshot_target_ts ON snapshot(target_id, ts);

CREATE TABLE IF NOT EXISTS price_point (
  target_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  price_low REAL NOT NULL,
  price_high REAL NOT NULL,
  confidence REAL NOT NULL,
  missing_fields TEXT NOT NULL DEFAULT '[]',
  discontinuity INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (target_id, ts)
);

CREATE TABLE IF NOT EXISTS event (
  id TEXT PRIMARY KEY,
  target_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  severity TEXT NOT NULL,
  gate_level TEXT NOT NULL,
  suppressed INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  evidence TEXT NOT NULL DEFAULT '[]',
  rule_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_event_ts ON event(ts DESC);

CREATE TABLE IF NOT EXISTS suggestion (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  action TEXT NOT NULL,
  impact_low REAL,
  impact_high REAL,
  confidence REAL NOT NULL,
  gate_level TEXT NOT NULL,
  narrative TEXT NOT NULL,
  generated_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  mode TEXT NOT NULL DEFAULT 'manual',
  exception INTEGER NOT NULL DEFAULT 0,
  exception_reason TEXT,
  decided_at TEXT,
  decision_meta TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_suggestion_event ON suggestion(event_id);

CREATE TABLE IF NOT EXISTS action_log (
  id TEXT PRIMARY KEY,
  suggestion_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT,
  at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "case" (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  event_type TEXT NOT NULL,
  price_band TEXT NOT NULL,
  delta_pct REAL,
  summary TEXT NOT NULL,
  attribution TEXT NOT NULL,
  decision TEXT,
  outcome_7d TEXT,
  ts TEXT NOT NULL,
  embed_provider TEXT NOT NULL,
  dim INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  file_name TEXT,
  rows_in INTEGER NOT NULL,
  rows_ok INTEGER NOT NULL,
  rows_dup INTEGER NOT NULL DEFAULT 0,
  rows_rejected INTEGER NOT NULL,
  errors TEXT NOT NULL DEFAULT '[]',
  received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS my_product (
  sku TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  price REAL,
  category TEXT,
  image_url TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mapping (
  id TEXT PRIMARY KEY,
  my_sku TEXT NOT NULL,
  target_id TEXT NOT NULL,
  score REAL,
  method TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT,
  UNIQUE (my_sku, target_id)
);

CREATE TABLE IF NOT EXISTS outcome (
  id TEXT PRIMARY KEY,
  suggestion_id TEXT NOT NULL UNIQUE,
  result TEXT NOT NULL,
  note TEXT,
  sales_delta REAL,
  recorded_by TEXT,
  recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_run (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  detail TEXT
);

CREATE TABLE IF NOT EXISTS model_call (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  model TEXT NOT NULL,
  ok INTEGER NOT NULL,
  fallback INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_model_call_created ON model_call(created_at);

CREATE TABLE IF NOT EXISTS approval_log (
  id TEXT PRIMARY KEY,
  suggestion_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  note TEXT,
  at TEXT NOT NULL,
  seq INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_approval_suggestion ON approval_log(suggestion_id);

CREATE TABLE IF NOT EXISTS app_user (
  username TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  display_name TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_token (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  prefix TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  scopes TEXT NOT NULL DEFAULT '["ingest"]',
  created_by TEXT,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  call_count INTEGER NOT NULL DEFAULT 0,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_api_token_hash ON api_token(token_hash);

CREATE TABLE IF NOT EXISTS finetune_job (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_model TEXT NOT NULL,
  method TEXT NOT NULL,
  teacher TEXT,
  dataset_path TEXT,
  config_path TEXT,
  samples INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  detail TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_run (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  suggestion_id TEXT,
  trigger TEXT NOT NULL DEFAULT 'manual',
  status TEXT NOT NULL,
  model TEXT,
  plan TEXT,
  step_count INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  error TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_agent_run_event ON agent_run(event_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_started ON agent_run(started_at DESC);

CREATE TABLE IF NOT EXISTS agent_step (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  input TEXT,
  output TEXT,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_agent_step_run ON agent_step(run_id, seq);

CREATE TABLE IF NOT EXISTS doc (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT,
  category TEXT,
  version TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_chunk (
  id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  chunk_no INTEGER NOT NULL,
  content TEXT NOT NULL,
  embed_provider TEXT NOT NULL,
  dim INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  parent_id TEXT,
  level TEXT NOT NULL DEFAULT 'child'
);
CREATE INDEX IF NOT EXISTS ix_doc_chunk_doc ON doc_chunk(doc_id, chunk_no);

CREATE TABLE IF NOT EXISTS skill (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  event_types TEXT NOT NULL DEFAULT '[]',
  min_severity TEXT,
  playbook TEXT NOT NULL,
  allowed_tools TEXT NOT NULL DEFAULT '[]',
  stages TEXT NOT NULL DEFAULT '[]',
  output_schema TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_case (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  payload TEXT NOT NULL,
  expected_action TEXT NOT NULL,
  expected_event_type TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_run (
  id TEXT PRIMARY KEY,
  run_key TEXT NOT NULL,
  total INTEGER NOT NULL,
  passed INTEGER NOT NULL,
  accuracy REAL NOT NULL,
  results TEXT NOT NULL,
  tier TEXT,
  metrics TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eval_run_created ON eval_run(created_at DESC);

CREATE TABLE IF NOT EXISTS eval_badcase (
  id TEXT PRIMARY KEY,
  run_key TEXT NOT NULL,
  case_name TEXT NOT NULL,
  segment TEXT,
  difficulty TEXT,
  reason TEXT,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eval_badcase_run ON eval_badcase(run_key);

CREATE TABLE IF NOT EXISTS judge_cache (
  key TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  rubric_version TEXT NOT NULL,
  verdict TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_memory (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  payload TEXT,
  weight REAL NOT NULL DEFAULT 1.0,
  created_at TEXT NOT NULL,
  last_used TEXT
);
CREATE INDEX IF NOT EXISTS ix_agent_memory_run ON agent_memory(run_id);

CREATE TABLE IF NOT EXISTS span (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  parent_id TEXT,
  run_id TEXT,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  attributes TEXT,
  started_at TEXT,
  duration_ms INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_span_trace ON span(trace_id);

CREATE TABLE IF NOT EXISTS execution (
  id TEXT PRIMARY KEY,
  suggestion_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  request TEXT,
  response TEXT,
  external_id TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  actor TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  rolled_back_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_execution_suggestion ON execution(suggestion_id);

CREATE TABLE IF NOT EXISTS bid_ledger (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  target_id TEXT NOT NULL,
  region TEXT,
  action TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'auto',
  status TEXT NOT NULL,
  from_price REAL,
  to_price REAL,
  delta_pct REAL,
  margin_at_target REAL,
  guardrail TEXT,
  suggestion_id TEXT,
  execution_id TEXT,
  run_id TEXT,
  strategy TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bid_ledger_region_ts
  ON bid_ledger(region, ts DESC);
CREATE INDEX IF NOT EXISTS ix_bid_ledger_target_ts
  ON bid_ledger(target_id, ts DESC);

CREATE TABLE IF NOT EXISTS collect_task (
  id TEXT PRIMARY KEY,
  target_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  interval_s INTEGER NOT NULL DEFAULT 0,
  next_run_at TEXT,
  locked_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_collect_task_pick
  ON collect_task(channel, status, next_run_at);

CREATE TABLE IF NOT EXISTS collect_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  task_id TEXT,
  channel TEXT NOT NULL,
  account TEXT,
  shop TEXT,
  status_code INTEGER,
  latency_ms INTEGER,
  outcome TEXT NOT NULL,
  error_kind TEXT,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_collect_log_ts ON collect_log(ts DESC);

CREATE TABLE IF NOT EXISTS manual_review (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  target_id TEXT,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS ix_manual_review_status
  ON manual_review(status, created_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


_pool = None


def _pg_pool():
    global _pool
    if _pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=int(os.getenv("LIRA_DB_POOL_MIN", "1")),
            max_size=int(os.getenv("LIRA_DB_POOL_MAX", "10")),
            max_idle=float(os.getenv("LIRA_DB_POOL_IDLE", "180")),
            timeout=10.0,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


_DATETIME_LITERALS = (
    (r"datetime\(\s*'now'\s*,\s*'-1 day'\s*\)", "(now() + interval '-1 day')"),
    (r"datetime\(\s*'now'\s*,\s*'-7 days'\s*\)", "(now() + interval '-7 days')"),
)


def to_backend_sql(sql: str, *, bind: bool = True) -> str:
    """把 SQL 占位符与时间函数收敛成 PostgreSQL 可执行的写法。

    bind=True 时按 psycopg 的客户端绑定规则转义百分号，避免正文里的 `%` 被当成占位符。
    """
    for pattern, repl in _DATETIME_LITERALS:
        sql = re.sub(pattern, repl, sql)
    sql = re.sub(r"datetime\(\s*'now'\s*,\s*\?\s*\)", "(now() + (?)::interval)", sql)
    sql = re.sub(
        r"datetime\(\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)",
        r"(\1)::timestamptz",
        sql,
    )
    if bind:
        sql = sql.replace("%", "%%")
    return sql.replace("?", "%s")


class _PgConnection:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def execute(self, sql: str, params=None):
        if params is None:
            return self._conn.execute(to_backend_sql(sql, bind=False))
        return self._conn.execute(to_backend_sql(sql), params)

    def executemany(self, sql: str, params_seq) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(to_backend_sql(sql), params_seq)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._pool.putconn(self._conn)


def connect():
    pool = _pg_pool()
    return _PgConnection(pool.getconn(), pool)


@contextmanager
def get_db() -> Iterator[Any]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pg_schema() -> list[str]:
    ddl = SCHEMA.replace("BLOB", "BYTEA").replace("REAL", "DOUBLE PRECISION")
    ddl = ddl.replace(
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
    )
    return [part.strip() for part in ddl.split(";") if part.strip()]


def init_db() -> None:
    _init_postgres()


def _init_postgres() -> None:
    with get_db() as conn:
        for statement in _pg_schema():
            conn.execute(statement)
        _ensure_all_columns(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_price_point_target_ts"
            " ON price_point(target_id, ts DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_event_open_ts"
            " ON event(ts DESC) WHERE suppressed = 0"
        )
    with get_db() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    try:
        with get_db() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            conn.execute(
                'CREATE INDEX IF NOT EXISTS ix_case_trgm ON "case"'
                " USING gin ((summary || ' ' || attribution) gin_trgm_ops)"
            )
    except Exception:
        # 没有扩展权限时退化为顺序扫描，不影响结果正确性
        pass


def _ensure_all_columns(conn) -> None:
    _ensure_column(conn, "app_user", "display_name", "TEXT")
    _ensure_column(conn, "suggestion", "case_ids", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "suggestion", "actor", "TEXT")
    _ensure_column(conn, "event", "snapshot_id", "TEXT")
    _ensure_column(conn, "target", "mapping_status", "TEXT DEFAULT 'unmapped'")
    _ensure_column(conn, "target", "holdout", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "snapshot", "image_fingerprint", "TEXT")
    _ensure_column(conn, "snapshot", "screenshot_ref", "TEXT")
    # 毛利护栏
    _ensure_column(conn, "my_product", "cost", "REAL")
    _ensure_column(conn, "my_product", "margin_floor", "REAL DEFAULT 0.15")
    _ensure_column(conn, "suggestion", "target_price", "REAL")
    _ensure_column(conn, "suggestion", "margin_at_target", "REAL")
    _ensure_column(conn, "suggestion", "margin_floor", "REAL")
    _ensure_column(conn, "suggestion", "guardrail", "TEXT DEFAULT 'unknown'")
    _ensure_column(conn, "suggestion", "guardrail_note", "TEXT")
    _ensure_column(conn, "doc_chunk", "parent_id", "TEXT")
    _ensure_column(conn, "doc_chunk", "level", "TEXT NOT NULL DEFAULT 'child'")
    _ensure_column(conn, "skill", "stages", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "skill", "output_schema", "TEXT")
    _ensure_column(conn, "collect_task", "interval_s", "INTEGER NOT NULL DEFAULT 0")
    # 向量已迁到 PGVector，旧库里的 embedding 列不再写入
    _drop_column(conn, "case", "embedding")
    _drop_column(conn, "doc_chunk", "embedding")
    _ensure_column(conn, "suggestion", "executed_price", "REAL")
    _ensure_column(conn, "suggestion", "submitted_by", "TEXT")
    _ensure_column(conn, "suggestion", "approved_by", "TEXT")
    _ensure_column(conn, "approval_log", "seq", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "suggestion", "agent_run_id", "TEXT")
    _ensure_column(conn, "agent_run", "skill_id", "TEXT")
    _ensure_column(conn, "suggestion", "executed_at", "TEXT")
    _ensure_column(conn, "suggestion", "execution_id", "TEXT")
    # 自主竞价：地区、策略、自动/异常分流
    _ensure_column(conn, "target", "region", "TEXT NOT NULL DEFAULT '全国'")
    _ensure_column(conn, "target", "pricing_strategy", "TEXT NOT NULL DEFAULT 'follow'")
    _ensure_column(conn, "target", "url", "TEXT")
    _ensure_column(conn, "target", "price_selector", "TEXT")
    _ensure_column(conn, "suggestion", "mode", "TEXT NOT NULL DEFAULT 'manual'")
    _ensure_column(conn, "suggestion", "exception", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "suggestion", "exception_reason", "TEXT")
    _ensure_column(conn, "suggestion", "decided_at", "TEXT")
    _ensure_column(conn, "suggestion", "decision_meta", "TEXT")
    _ensure_column(conn, "model_call", "run_id", "TEXT")
    _ensure_column(conn, "model_call", "prompt_tokens", "INTEGER")
    _ensure_column(conn, "model_call", "completion_tokens", "INTEGER")
    _ensure_column(conn, "model_call", "cost", "REAL")
    _ensure_column(conn, "model_call", "provider", "TEXT")
    _ensure_column(conn, "model_call", "prompt_name", "TEXT")
    _ensure_column(conn, "model_call", "prompt_version", "TEXT")
    _ensure_column(conn, "model_call", "trace_id", "TEXT")
    _ensure_column(conn, "agent_run", "prompt_tokens", "INTEGER")
    _ensure_column(conn, "agent_run", "completion_tokens", "INTEGER")
    _ensure_column(conn, "agent_run", "cost", "REAL")
    _ensure_column(conn, "eval_run", "tier", "TEXT")
    _ensure_column(conn, "eval_run", "metrics", "TEXT")


def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    conn.execute(
        f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS {column} '
        f'{ddl.replace("REAL", "DOUBLE PRECISION")}'
    )


def _drop_column(conn, table: str, column: str) -> None:
    conn.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS {column}')


def row_to_dict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def is_unique_violation(exc: Exception) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UniqueViolation)


def is_db_error(exc: Exception) -> bool:
    import psycopg

    return isinstance(exc, psycopg.Error)


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
