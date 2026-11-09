import uuid

import pytest

from app import db
from app.vectorstore import PgVectorStore, Point, table_name


@pytest.fixture
def store() -> PgVectorStore:
    return PgVectorStore()


@pytest.fixture
def collection():
    name = f"test_{uuid.uuid4().hex[:10]}"
    yield name
    with db.get_db() as conn:
        conn.execute(f'DROP TABLE IF EXISTS "{table_name(name)}"')


def test_upsert_and_search_returns_nearest(store, collection):
    store.upsert(
        collection,
        [
            Point("a", [1.0, 0.0], {"event_type": "price_drop"}),
            Point("b", [0.0, 1.0], {"event_type": "price_rise"}),
        ],
    )
    hits = store.search(collection, [1.0, 0.1], top_k=1)
    assert hits[0].id == "a"
    assert hits[0].payload["event_type"] == "price_drop"
    assert hits[0].score > 0.9


def test_filter_is_applied_before_search(store, collection):
    store.upsert(
        collection,
        [
            Point("a", [1.0, 0.0], {"event_type": "price_drop"}),
            Point("b", [0.9, 0.1], {"event_type": "price_rise"}),
        ],
    )
    hits = store.search(collection, [1.0, 0.0], filters={"event_type": "price_rise"})
    assert [h.id for h in hits] == ["b"]


def test_upsert_same_id_is_idempotent(store, collection):
    point = Point("a", [1.0, 0.0], {"event_type": "price_drop"})
    store.upsert(collection, [point])
    store.upsert(collection, [point])
    assert store.count(collection) == 1


def test_delete_removes_points(store, collection):
    store.upsert(collection, [Point("a", [1.0, 0.0], {}), Point("b", [0.0, 1.0], {})])
    store.delete(collection, ["a"])
    assert store.count(collection) == 1


def test_dimension_mismatch_is_rejected(store, collection):
    store.upsert(collection, [Point("a", [1.0, 0.0], {})])
    with pytest.raises(ValueError):
        store.upsert(collection, [Point("b", [1.0, 0.0, 0.0], {})])


def test_search_missing_collection_returns_empty(store):
    assert store.search(f"missing_{uuid.uuid4().hex[:8]}", [1.0, 0.0]) == []
