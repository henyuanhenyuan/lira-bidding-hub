from app import retrieval_service, tracing


def test_heuristic_variants_strip_stopwords():
    variants = retrieval_service.heuristic_variants("价格带击穿的判定标准是什么？")
    assert variants, "应至少产出一个变体"
    assert all("什么" not in item for item in variants)


def test_rewrite_query_without_llm(monkeypatch):
    monkeypatch.setattr(retrieval_service.agent, "_llm_available", lambda: False)
    tracing.new_trace()
    variants = retrieval_service.rewrite_query("L3 事件需要什么数据源？")
    assert variants
    assert all(item.strip() for item in variants)


def test_fuse_dedupes_and_orders():
    fused = retrieval_service._fuse([
        [{"id": "a", "content": "x"}, {"id": "b", "content": "y"}],
        [{"id": "b", "content": "y"}, {"id": "c", "content": "z"}],
    ])
    assert [item["id"] for item in fused] == ["b", "a", "c"]
    assert fused[0]["score"] > fused[1]["score"]


def test_multi_hop_triggers_second_query():
    calls: list[str] = []

    def fake(text, size):
        calls.append(text)
        return [{"id": "a", "content": "价格带击穿规则正文", "doc_title": "价格带规则"}]

    tracing.new_trace()
    retrieval_service.search_docs(
        None, "击穿", limit=2, rewrite=False, multi_hop=True, search=fake
    )
    assert len(calls) >= 2
    tree = tracing.list_trace(tracing.current_trace())
    names = [node["name"] for node in tree["roots"]]
    assert any("retrieval" in name for name in names)


def test_empty_search_returns_empty():
    results = retrieval_service.search_docs(
        None, "不存在的内容", limit=3, rewrite=False, multi_hop=False,
        search=lambda text, size: [],
    )
    assert results == []
