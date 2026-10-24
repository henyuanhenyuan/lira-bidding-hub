from app import evidence


def test_all_ids_valid():
    r = evidence.validate(["a", "b"], {"a", "b", "c"})
    assert r.ok is True
    assert r.valid == ["a", "b"]
    assert r.invalid == []


def test_unknown_id_rejects_whole_claim():
    r = evidence.validate(["a", "zzz"], {"a", "b"})
    assert r.ok is False
    assert r.invalid == ["zzz"]


def test_empty_evidence_is_not_ok():
    r = evidence.validate([], {"a"})
    assert r.ok is False


def test_confidence_ceiling_by_evidence_count():
    assert evidence.confidence_ceiling(0, 0.99) <= 0.30
    assert evidence.confidence_ceiling(1, 0.99) <= 0.60
    assert evidence.confidence_ceiling(2, 0.99) <= 0.80
    assert evidence.confidence_ceiling(3, 0.99) == 0.95
