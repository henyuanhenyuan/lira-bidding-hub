from app import rerank


CASES = [
    {"id": "a", "summary": "竞品降价 10%", "attribution": "大促试探", "price_band": "250-300", "delta_pct": -0.10, "ts": None},
    {"id": "b", "summary": "竞品提价", "attribution": "换代升级", "price_band": "200-250", "delta_pct": 0.12, "ts": None},
]


def test_without_url_uses_rule_rerank(monkeypatch):
    monkeypatch.setattr(rerank, "RERANK_URL", "")
    out = rerank.rerank(CASES, query="竞品降价", price_band="250-300", delta_pct=-0.10)
    assert [c["id"] for c in out][0] == "a"


def test_model_rerank_can_reorder(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"results": [{"index": 1, "relevance_score": 0.9},
                                {"index": 0, "relevance_score": 0.1}]}

    monkeypatch.setattr(rerank, "RERANK_URL", "http://rerank.test")
    monkeypatch.setattr(rerank.httpx, "post", lambda *a, **k: FakeResponse())
    out = rerank.rerank(CASES, query="竞品降价", price_band=None, delta_pct=None)
    assert [c["id"] for c in out] == ["b", "a"]


def test_model_failure_falls_back(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(rerank, "RERANK_URL", "http://rerank.test")
    monkeypatch.setattr(rerank.httpx, "post", boom)
    out = rerank.rerank(CASES, query="竞品降价", price_band="250-300", delta_pct=-0.10)
    assert [c["id"] for c in out][0] == "a"


def test_empty_cases_short_circuit():
    assert rerank.rerank([], query="x", price_band=None, delta_pct=None) == []
