import pytest

from app import db
from app.evaluation import datasets


def test_golden_cases_load_and_are_unique():
    cases = datasets.load()
    assert len(cases) == 120
    names = [case.name for case in cases]
    assert len(names) == len(set(names))
    segments = {case.segment for case in cases}
    assert segments == {
        "price_event", "guardrail", "injection",
        "low_confidence", "sop_boundary",
    }


def test_golden_expected_actions_are_legal():
    legal = {"hold", "follow", "adjust_coupon", "no_action", "adjust_price", "join_promo"}
    for case in datasets.load():
        assert case.expected_action in legal, case.name
        assert case.payload.get("snapshots"), case.name


def test_tier_selection_is_nested():
    cases = datasets.load()
    smoke = datasets.select(cases, "smoke")
    core = datasets.select(cases, "core")
    full = datasets.select(cases, "full")
    assert 0 < len(smoke) <= len(core) <= len(full) == 120
    assert all(case.difficulty == "easy" for case in smoke)


def test_unknown_tier_rejected():
    with pytest.raises(ValueError):
        datasets.select(datasets.load(), "nope")


def test_seed_is_idempotent():
    cases = datasets.select(datasets.load(), "smoke")
    with db.get_db() as conn:
        first = datasets.seed(conn, cases)
        second = datasets.seed(conn, cases)
        count = conn.execute("SELECT COUNT(*) AS c FROM eval_case").fetchone()["c"]
    assert first == len(cases)
    assert second == 0
    assert count == len(cases)
