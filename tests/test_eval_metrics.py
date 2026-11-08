from app.evaluation import metrics


def _result(**overrides):
    base = {
        "case": "c", "passed": True, "actual_action": "hold",
        "expected_action": "hold", "evidence_count": 1, "trace_ok": True,
        "segment": "price_event", "difficulty": "easy", "latency_ms": 10,
    }
    base.update(overrides)
    return base


def test_action_accuracy_counts_mismatch():
    results = [
        _result(),
        _result(actual_action="follow", passed=False),
        _result(actual_action="no_action", passed=False),
        _result(),
    ]
    assert metrics.action_accuracy(results) == 0.5


def test_evidence_closure_rate_requires_evidence():
    results = [_result(), _result(evidence_count=0, passed=False)]
    assert metrics.evidence_closure_rate(results) == 0.5


def test_trace_completion_rate():
    results = [_result(), _result(trace_ok=False, passed=False)]
    assert metrics.trace_completion_rate(results) == 0.5


def test_citation_validity_rejects_foreign_ids():
    assert metrics.citation_validity(["doc:1", "doc:x"], ["doc:1", "doc:2"]) == 0.5
    assert metrics.citation_validity([], ["doc:1"]) == 0.0


def test_recall_at_k_and_mrr():
    retrieved = ["a", "b", "c", "d", "e", "f"]
    assert metrics.recall_at_k(["c", "z"], retrieved, k=5) == 0.5
    assert metrics.recall_at_k(["z"], retrieved, k=5) == 0.0
    assert metrics.reciprocal_rank(["c"], retrieved) == 0.3333
    assert metrics.reciprocal_rank(["f"], retrieved) == 0.1667
    assert metrics.reciprocal_rank(["i"], retrieved) == 0.0


def test_cohen_kappa_perfect_and_chance():
    labels = ["pass", "fail", "pass", "fail"]
    assert metrics.cohen_kappa(labels, labels) == 1.0
    assert metrics.cohen_kappa(["pass", "pass"], ["fail", "fail"]) == 0.0
    assert metrics.cohen_kappa([], []) == 0.0


def test_aggregate_slices_by_segment():
    results = [
        _result(segment="price_event"),
        _result(segment="price_event", actual_action="follow", passed=False),
        _result(segment="injection", difficulty="hard"),
    ]
    summary = metrics.aggregate(results)
    assert summary["total"] == 3
    assert summary["action_accuracy"] == 0.6667
    assert summary["by_segment"]["price_event"]["total"] == 2
    assert summary["by_segment"]["price_event"]["passed"] == 1
    assert summary["by_difficulty"]["hard"]["total"] == 1


def test_compare_floor_and_delta():
    baseline = {"action_accuracy": 0.95, "evidence_closure_rate": 1.0,
                "trace_completion_rate": 1.0}
    good = {"action_accuracy": 0.94, "evidence_closure_rate": 1.0,
            "trace_completion_rate": 1.0}
    assert metrics.compare(good, baseline) == []

    worse = {"action_accuracy": 0.90, "evidence_closure_rate": 1.0,
             "trace_completion_rate": 1.0}
    violations = metrics.compare(worse, baseline)
    assert [item["kind"] for item in violations] == ["delta"]

    broken = {"action_accuracy": 0.95, "evidence_closure_rate": 0.5,
              "trace_completion_rate": 1.0}
    violations = metrics.compare(broken, baseline)
    assert violations[0]["metric"] == "evidence_closure_rate"
    assert violations[0]["kind"] == "floor"
