from app import assertions


def test_currency_price_matches_allowed():
    assert assertions.verify("到手价 ¥1,299", allowed=[1299.0]) == []


def test_plain_price_with_unit_matches():
    assert assertions.verify("降到 269 元", allowed=[269.0]) == []


def test_percent_matches_fraction_or_number():
    assert assertions.verify("降幅 10%", allowed=[0.10]) == []
    assert assertions.verify("降幅 10%", allowed=[10.0]) == []


def test_discount_matches_fraction():
    assert assertions.verify("打到 8.5 折", allowed=[0.85]) == []


def test_invented_number_is_flagged():
    violations = assertions.verify("竞品降到了 999 元", allowed=[269.0])
    assert len(violations) == 1
    assert violations[0].value == 999.0


def test_bare_counts_are_ignored():
    assert assertions.verify("7 天内可申请价保", allowed=[]) == []


def test_facts_to_numbers_covers_price_and_delta():
    numbers = assertions.facts_to_numbers(
        {"price_low": 199.0, "price_high": 201.0, "confidence": 0.9,
         "prev_point": 220.0, "delta_pct": -0.0955}
    )
    assert 199.0 in numbers
    assert 0.0955 in numbers
    assert 9.55 in numbers
