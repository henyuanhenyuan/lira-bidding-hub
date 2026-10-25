from fastapi.testclient import TestClient

from app import agent, db, docs
from app.main import app

client = TestClient(app)

CONTENT = """# 大促价保规则

大促期间商品降价后，消费者可在 7 天内申请价保。价保金额按实际支付价差计算。

## 活动叠加

店铺券与跨店满减可以叠加，但同一订单最多使用一张店铺券。直播专享价不参与价保。

## 采集与判定

竞品价格下降超过 20% 时，先确认是否为直播专享价或限时秒杀，再判断是否跟进。
"""


def test_split_text_respects_size_and_heading():
    chunks = docs.split_text(CONTENT, max_chars=120, overlap=20)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert chunks[0].startswith("# 大促价保规则")


LONG_CONTENT = "\n\n".join(
    f"## 第 {i} 条规则\n\n" + "竞品价格变动需要结合活动类型判断，" * 12
    for i in range(1, 7)
)


def test_hierarchy_has_parents_and_children():
    with db.get_db() as conn:
        doc = docs.create_doc(conn, title="长规则", content=LONG_CONTENT)
        rows = conn.execute(
            "SELECT id, level, parent_id FROM doc_chunk WHERE doc_id = ?"
            " ORDER BY chunk_no",
            (doc["id"],),
        ).fetchall()
    parents = [row for row in rows if row["level"] == "parent"]
    children = [row for row in rows if row["level"] == "child"]
    assert parents
    assert children
    parent_ids = {row["id"] for row in parents}
    assert all(child["parent_id"] in parent_ids for child in children)


def test_search_returns_parent_context():
    with db.get_db() as conn:
        docs.create_doc(conn, title="长规则", content=LONG_CONTENT)
        found = docs.search_docs(conn, "竞品价格变动 活动类型", limit=3)
    assert found
    assert found[0]["parent_content"]
    assert len(found[0]["parent_content"]) >= len(found[0]["content"])


def test_create_and_search_doc():
    with db.get_db() as conn:
        doc = docs.create_doc(
            conn, title="大促价保规则", content=CONTENT, source="平台规则",
            category="活动", version="2026-10",
        )
    assert doc["chunk_count"] >= 1
    with db.get_db() as conn:
        found = docs.search_docs(conn, "价保 7 天", limit=3)
    assert found
    assert found[0]["doc_title"] == "大促价保规则"
    assert found[0]["content"]


def test_api_docs_crud():
    created = client.post(
        "/api/docs",
        json={"title": "活动玩法", "content": CONTENT, "category": "活动"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["chunk_count"] >= 1

    listing = client.get("/api/docs").json()
    assert any(item["id"] == body["id"] for item in listing)

    detail = client.get(f"/api/docs/{body['id']}").json()
    chunk_id = detail["chunks"][0]["id"]
    chunk = client.get(f"/api/doc-chunks/{chunk_id}").json()
    assert chunk["doc_title"] == "活动玩法"
    assert client.get("/api/doc-chunks/missing").status_code == 404


def test_agent_can_cite_doc():
    with db.get_db() as conn:
        doc = docs.create_doc(conn, title="规则", content=CONTENT)
    chunk = doc["chunks"][0]
    from app.contracts import PricePoint

    point = PricePoint(
        target_id="t1", ts="2026-10-24T02:17:00+08:00", point=199.0,
        price_low=197.0, price_high=201.0, confidence=0.9, missing_fields=[],
    )
    result = agent.analyze(
        event_type="price_drop",
        severity="L3",
        gate="strong",
        title="竞品A",
        point=point,
        prev=None,
        allowed_evidence=["snap:x"],
        docs=[{**chunk, "doc_title": "规则"}],
        force_template=True,
    )
    assert f"doc:{chunk['id']}" in result.evidence_ids


def test_graph_includes_doc_evidence(monkeypatch):
    with db.get_db() as conn:
        doc = docs.create_doc(conn, title="大促价保规则", content=CONTENT)
    chunk = doc["chunks"][0]
    fake = [
        {
            "id": chunk["id"], "doc_id": doc["id"], "doc_title": doc["title"],
            "chunk_no": chunk["chunk_no"], "content": chunk["content"],
            "score": 0.9,
        }
    ]
    monkeypatch.setattr(
        docs, "search_docs", lambda conn, query, limit=3: fake
    )

    client.post(
        "/v1/ingest/snapshots",
        json={
            "snapshots": [
                {
                    "target_id": "t1", "ts": "2026-10-23T02:00:00+08:00",
                    "collector": "eval", "source_tier": 1,
                    "observation": {"list_price": 299, "title": "竞品A"},
                },
                {
                    "target_id": "t1", "ts": "2026-10-24T02:00:00+08:00",
                    "collector": "eval", "source_tier": 1,
                    "observation": {"list_price": 199, "title": "竞品A"},
                },
            ]
        },
    )
    event = client.get("/api/events").json()[0]
    suggestion = client.post(f"/api/events/{event['id']}/analyze").json()
    detail = client.get(f"/api/events/{event['id']}").json()

    assert f"doc:{chunk['id']}" in detail["evidence"]
    suggestion_detail = client.get(f"/api/suggestions/{suggestion['id']}").json()
    assert suggestion_detail["evidence_docs"][0]["doc_title"] == "大促价保规则"
