from app import db, memory


def test_remember_and_recall_by_query():
    memory.remember("run-1", memory.SESSION, "竞品A 降价 25% 建议投券", {"a": 1})
    memory.remember("run-2", memory.SESSION, "竞品B 提价 观察")

    items = memory.recall(run_id="run-1", query="竞品A")
    assert len(items) == 1
    assert "投券" in items[0]["summary"]
    assert items[0]["payload"] == {"a": 1}


def test_recall_text_joins_lines():
    memory.remember("run-9", memory.SESSION, "记忆一")
    memory.remember("run-9", memory.SESSION, "记忆二")
    text = memory.recall_text(run_id="run-9", limit=2)
    assert "记忆一" in text and "记忆二" in text


def test_purge_expired_removes_old_rows():
    memory.remember("run-old", memory.SESSION, "旧记忆")
    with db.get_db() as conn:
        conn.execute(
            "UPDATE agent_memory SET created_at = '2000-01-01T00:00:00+00:00'"
        )
    assert memory.purge_expired(ttl_seconds=60) == 1
    assert memory.recall(run_id="run-old") == []
