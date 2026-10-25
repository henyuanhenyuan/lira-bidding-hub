import fakeredis

from app import risk


def _client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_classify_status_codes():
    assert risk.classify(status_code=403) == "forbidden"
    assert risk.classify(status_code=429) == "rate_limited"
    assert risk.classify(status_code=200, body="正常商品页") is None


def test_classify_body_markers():
    assert risk.classify(status_code=200, body="请输入验证码后继续") == "captcha"
    assert risk.classify(status_code=200, body="请重新登录") == "auth_expired"
    assert risk.classify(status_code=200, body="访问受限") == "forbidden"


def test_circuit_opens_after_threshold():
    client = _client()
    for _ in range(2):
        state = risk.record_failure(
            "rpa", "acc1", "shop1", kind="forbidden",
            threshold=3, cooldown_s=600, client=client, now=1000.0,
        )
        assert state == "closed"
    state = risk.record_failure(
        "rpa", "acc1", "shop1", kind="forbidden",
        threshold=3, cooldown_s=600, client=client, now=1000.0,
    )
    assert state == "open"
    assert risk.allow("rpa", "acc1", "shop1", client=client, now=1000.0) is False
    assert risk.state("rpa", "acc1", "shop1", client=client, now=1000.0) == "open"


def test_circuit_half_open_after_cooldown():
    client = _client()
    risk.record_failure(
        "rpa", "acc1", "shop1", kind="rate_limited",
        threshold=1, cooldown_s=60, client=client, now=1000.0,
    )
    assert risk.allow("rpa", "acc1", "shop1", client=client, now=1030.0) is False
    assert risk.allow("rpa", "acc1", "shop1", client=client, now=1061.0) is True
    assert risk.state("rpa", "acc1", "shop1", client=client, now=1061.0) == "half_open"


def test_success_closes_circuit():
    client = _client()
    risk.record_failure(
        "api", "acc1", "shop1", kind="forbidden",
        threshold=1, cooldown_s=600, client=client, now=1000.0,
    )
    risk.record_success("api", "acc1", "shop1", client=client)
    assert risk.allow("api", "acc1", "shop1", client=client, now=1001.0) is True
    assert risk.state("api", "acc1", "shop1", client=client, now=1001.0) == "closed"


def test_dimensions_isolated():
    client = _client()
    risk.record_failure(
        "rpa", "acc1", "shop1", kind="forbidden",
        threshold=1, cooldown_s=600, client=client, now=1000.0,
    )
    assert risk.allow("rpa", "acc1", "shop2", client=client, now=1000.0) is True
