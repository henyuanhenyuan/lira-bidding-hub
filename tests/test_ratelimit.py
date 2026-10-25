import fakeredis

from app import ratelimit


def _client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_bucket_allows_up_to_capacity():
    client = _client()
    assert ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=2, client=client, now=1000.0
    )
    assert ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=2, client=client, now=1000.0
    )
    assert not ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=2, client=client, now=1000.0
    )


def test_bucket_refills_over_time():
    client = _client()
    assert ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=1, client=client, now=1000.0
    )
    assert not ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=1, client=client, now=1000.5
    )
    assert ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=1, client=client, now=1001.0
    )


def test_dimensions_are_isolated():
    client = _client()
    assert ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=1, client=client, now=1000.0
    )
    assert ratelimit.acquire(
        "rpa", "acc1", "shop2", rate=1.0, capacity=1, client=client, now=1000.0
    )
    assert ratelimit.acquire(
        "api", "acc1", "shop1", rate=1.0, capacity=1, client=client, now=1000.0
    )
    assert not ratelimit.acquire(
        "rpa", "acc1", "shop1", rate=1.0, capacity=1, client=client, now=1000.0
    )


def test_wait_seconds_reports_shortfall():
    client = _client()
    ratelimit.acquire("rpa", "a", "s", rate=0.5, capacity=1, client=client, now=1000.0)
    wait = ratelimit.wait_seconds("rpa", "a", "s", rate=0.5, client=client, now=1000.0)
    assert 1.9 <= wait <= 2.1
