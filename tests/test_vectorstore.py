import pytest
from qdrant_client import QdrantClient

from app.vectorstore import Point, QdrantVectorStore


def _store() -> QdrantVectorStore:
    return QdrantVectorStore(client=QdrantClient(":memory:"))


def test_upsert_and_search_returns_nearest():
    store = _store()
    store.upsert(
        "cases",
        [
            Point("a", [1.0, 0.0], {"event_type": "price_drop"}),
            Point("b", [0.0, 1.0], {"event_type": "price_rise"}),
        ],
    )
    hits = store.search("cases", [1.0, 0.1], top_k=1)
    assert hits[0].id == "a"
    assert hits[0].payload["event_type"] == "price_drop"
    assert hits[0].score > 0.9


def test_filter_is_applied_before_search():
    store = _store()
    store.upsert(
        "cases",
        [
            Point("a", [1.0, 0.0], {"event_type": "price_drop"}),
            Point("b", [0.9, 0.1], {"event_type": "price_rise"}),
        ],
    )
    hits = store.search("cases", [1.0, 0.0], filters={"event_type": "price_rise"})
    assert [h.id for h in hits] == ["b"]


def test_upsert_same_id_is_idempotent():
    store = _store()
    point = Point("a", [1.0, 0.0], {"event_type": "price_drop"})
    store.upsert("cases", [point])
    store.upsert("cases", [point])
    assert store.count("cases") == 1


def test_delete_removes_points():
    store = _store()
    store.upsert("cases", [Point("a", [1.0, 0.0], {}), Point("b", [0.0, 1.0], {})])
    store.delete("cases", ["a"])
    assert store.count("cases") == 1


def test_dimension_mismatch_is_rejected():
    store = _store()
    store.upsert("cases", [Point("a", [1.0, 0.0], {})])
    with pytest.raises(ValueError):
        store.upsert("cases", [Point("b", [1.0, 0.0, 0.0], {})])


def test_search_missing_collection_returns_empty():
    assert _store().search("nope", [1.0, 0.0]) == []
