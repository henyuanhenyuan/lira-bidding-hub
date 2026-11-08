from app import db
from app.evaluation import retrieval


def test_corpus_and_cases_load():
    corpus = retrieval.load_corpus()
    cases = retrieval.load_cases()
    assert len(corpus) >= 8
    assert len(cases) >= 10
    assert all(case.keywords for case in cases)


def test_seed_corpus_is_idempotent():
    with db.get_db() as conn:
        first = retrieval.seed_corpus(conn)
        second = retrieval.seed_corpus(conn)
    assert first >= 8
    assert second == 0


def test_retrieval_metrics_on_seeded_corpus():
    with db.get_db() as conn:
        retrieval.seed_corpus(conn)
        result = retrieval.evaluate(conn)
    assert result["cases"] >= 10
    assert 0.0 <= result["recall_at_k"] <= 1.0
    assert 0.0 <= result["mrr"] <= 1.0
    assert result["recall_at_k"] >= 0.8
    for item in result["per_case"]:
        assert set(item) >= {"query", "recall", "mrr", "matched_keywords"}


def test_evaluate_accepts_injected_search():
    cases = retrieval.load_cases()[:1]
    result = retrieval.evaluate(
        None, cases=cases, k=3,
        search=lambda query, limit: [{"content": " ".join(cases[0].keywords)}],
    )
    assert result["recall_at_k"] == 1.0
    assert result["mrr"] == 1.0


def test_empty_search_scores_zero():
    cases = retrieval.load_cases()[:2]
    result = retrieval.evaluate(None, cases=cases, search=lambda q, k: [])
    assert result["recall_at_k"] == 0.0
    assert result["mrr"] == 0.0
