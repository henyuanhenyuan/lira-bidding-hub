from app import db, reviews


def add(items, target="t1"):
    with db.get_db() as conn:
        return reviews.add_reviews(conn, target, items)


def test_add_and_dedupe():
    r1 = add([{"rating": 5, "content": "很好用"}])
    assert r1["inserted"] == 1
    r2 = add([{"rating": 5, "content": "很好用"}])
    assert r2["duplicates"] == 1
    r3 = add([{"rating": 5, "content": "   "}])
    assert r3["skipped"] == 1


def test_classify_hits_expected_topics():
    assert "物流发货" in reviews.classify("发货太慢了，物流不更新")
    assert "价格性价比" in reviews.classify("价格有点贵但划算")
    assert reviews.classify("今天天气不错") == set()


def test_is_negative_prefers_rating():
    assert reviews.is_negative(1, "还行")
    assert not reviews.is_negative(5, "有点贵")
    assert reviews.is_negative(None, "太差了")


def test_analyze_builds_topics_and_opportunities():
    add([
        {"rating": 2, "content": "发货太慢"},
        {"rating": 1, "content": "物流一直不更新"},
        {"rating": 2, "content": "快递慢"},
        {"rating": 5, "content": "味道很好闻"},
    ])
    with db.get_db() as conn:
        ins = reviews.analyze(conn, "t1", 7)
    assert ins["review_count"] == 4
    top = ins["topics"][0]
    assert top["name"] == "物流发货"
    assert top["negative_share"] == 1.0
    assert ins["opportunities"]
    assert ins["generated_by"]  # LLM 关闭时走模板


def test_analyze_returns_none_without_reviews():
    with db.get_db() as conn:
        assert reviews.analyze(conn, "nope", 7) is None


def test_negative_spike_emits_event():
    add([
        {"rating": 5, "content": "物流很快"},
        {"rating": 5, "content": "快递给力"},
        {"rating": 5, "content": "发货及时"},
    ])
    with db.get_db() as conn:
        first = reviews.analyze(conn, "t1", 7)
    assert first["event_id"] is None

    add([
        {"rating": 1, "content": "物流太慢"},
        {"rating": 1, "content": "快递迟迟不到"},
        {"rating": 1, "content": "发货等了一周"},
    ])
    with db.get_db() as conn:
        second = reviews.analyze(conn, "t1", 7)
        assert second["event_id"]
        ev = conn.execute(
            "SELECT * FROM event WHERE id = ?", (second["event_id"],)
        ).fetchone()
    assert ev["type"] == "review_spike"
    assert ev["severity"] == "L2"
    assert "物流发货" in ev["note"]


def test_spike_deduplicated_within_a_day():
    add([
        {"rating": 5, "content": "物流很快"},
        {"rating": 5, "content": "快递给力"},
        {"rating": 5, "content": "发货及时"},
    ])
    with db.get_db() as conn:
        reviews.analyze(conn, "t1", 7)
    add([
        {"rating": 1, "content": "物流太慢"},
        {"rating": 1, "content": "快递迟迟不到"},
        {"rating": 1, "content": "发货等了一周"},
    ])
    with db.get_db() as conn:
        second = reviews.analyze(conn, "t1", 7)
        third = reviews.analyze(conn, "t1", 7)
    assert second["event_id"]
    assert third["event_id"] is None


def test_latest_insight_returns_most_recent():
    add([{"rating": 2, "content": "包装破损"}])
    with db.get_db() as conn:
        reviews.analyze(conn, "t1", 7)
    add([{"rating": 1, "content": "包装漏了"}])
    with db.get_db() as conn:
        reviews.analyze(conn, "t1", 7)
        latest = reviews.latest_insight(conn, "t1")
    assert latest["review_count"] == 2
