from app import agent, cases, db
from app.contracts import PricePoint


def pt(v=269):
    return PricePoint(
        target_id="t1", ts="2026-10-24T02:17:00+08:00", point=v,
        price_low=v * 0.995, price_high=v * 1.005,
        confidence=0.87, missing_fields=[],
    )


def make_case(**kw):
    base = dict(
        category="洗护", event_type="price_drop", price_band="250-300",
        delta_pct=-0.10, summary="竞品大促前降价 10%",
        attribution="大促价格试探，72 小时内多半回调",
        decision="hold", outcome_7d="未跟价，7 日后回调",
    )
    base.update(kw)
    with db.get_db() as conn:
        return cases.create(conn, **base)


def test_price_band():
    assert cases.price_band_of(269) == "250-300"
    assert cases.price_band_of(89) == "50-100"
    assert cases.price_band_of(300) == "300-350"


def test_create_then_search_finds_it():
    cid = make_case()
    with db.get_db() as conn:
        found = cases.search(
            conn, query="竞品大促前降价", category=None,
            event_type="price_drop", price_band="250-300",
            delta_pct=-0.10, limit=3,
        )
    assert found
    assert found[0].id == cid
    assert found[0].attribution


def test_search_falls_back_when_no_filter_match():
    make_case(event_type="price_rise")
    with db.get_db() as conn:
        found = cases.search(
            conn, query="降价", category=None, event_type="price_drop",
            price_band=None, delta_pct=None, limit=3,
        )
    assert found  # 过滤为空时退化为全量


def test_seed_is_idempotent():
    with db.get_db() as conn:
        first = cases.seed(conn)
    assert first == len(cases.SEED_CASES)
    with db.get_db() as conn:
        assert cases.seed(conn) == 0
        assert cases.count(conn) == first


def test_embedding_falls_back_to_hash_without_llm():
    # conftest 里 LIRA_LLM=off，因此应走哈希向量
    make_case()
    with db.get_db() as conn:
        row = conn.execute('SELECT embed_provider, dim FROM "case"').fetchone()
    assert row["embed_provider"] == "hash:256"
    assert row["dim"] == 256


def test_case_vector_is_stored_in_qdrant():
    from app import embeddings, vectorstore

    cid = make_case()
    vec, provider = embeddings.embed("竞品大促前降价")
    store = vectorstore.QdrantVectorStore()
    hits = store.search(cases.collection_name(provider, len(vec)), vec, top_k=10)
    assert cid in [hit.id for hit in hits]


def test_agent_cites_retrieved_case(monkeypatch):
    monkeypatch.setattr(agent, "_llm_available", lambda: False)
    out = agent.analyze(
        event_type="price_drop", severity="L2", gate="strong", title="竞品A",
        point=pt(), prev=None, allowed_evidence=["snap:1"],
        cases=[{"id": "c1", "summary": "竞品降价", "attribution": "大促试探",
                "outcome_7d": None, "price_band": "250-300"}],
    )
    assert "case:c1" in out.evidence_ids
    assert "大促试探" in out.narrative


def test_agent_without_cases_has_no_case_evidence(monkeypatch):
    monkeypatch.setattr(agent, "_llm_available", lambda: False)
    out = agent.analyze(
        event_type="price_drop", severity="L2", gate="strong", title="竞品A",
        point=pt(), prev=None, allowed_evidence=["snap:1"],
    )
    assert all(not e.startswith("case:") for e in out.evidence_ids)
