import pytest

from app.llm.limiter import RateLimiter
from app.llm.providers.base import ProviderError
from app.llm.router import RateLimited, Router, _Breaker
from app.llm.types import ChatRequest, ChatResponse, Message, Usage


class FakeProvider:
    def __init__(self, name="fake", fail=False, transient=True):
        self.name = name
        self.fail = fail
        self.transient = transient
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        if self.fail:
            raise ProviderError("boom", transient=self.transient)
        return ChatResponse(
            text="ok", provider=self.name, model="m", usage=Usage(1, 1)
        )

    def stream(self, request):
        if self.fail:
            raise ProviderError("boom", transient=self.transient)
        yield "a"
        yield "b"

    def health(self):
        return True


def _router(providers, chain, rpm=60, retries=1):
    ticks = [0.0]

    def clock():
        ticks[0] += 10.0
        return ticks[0]

    return Router(
        providers={p.name: p for p in providers},
        chains={"default": chain},
        limiter=RateLimiter(rpm, clock=clock),
        max_retries=retries,
        sleep=lambda _: None,
    )


def _request():
    return ChatRequest(messages=(Message("user", "hi"),))


def test_fallback_to_second_provider_on_transient_error():
    bad = FakeProvider("bad", fail=True)
    good = FakeProvider("good")
    router = _router([bad, good], ["bad", "good"])
    response = router.complete("analysis", _request())
    assert response.provider == "good"
    assert bad.calls == 2  # 首次 + 一次重试


def test_non_transient_error_skips_retry():
    bad = FakeProvider("bad", fail=True, transient=False)
    good = FakeProvider("good")
    router = _router([bad, good], ["bad", "good"])
    assert router.complete("analysis", _request()).provider == "good"
    assert bad.calls == 1


def test_all_providers_fail_raises():
    router = _router(
        [FakeProvider("a", fail=True), FakeProvider("b", fail=True)], ["a", "b"]
    )
    with pytest.raises(ProviderError):
        router.complete("analysis", _request())


def test_circuit_breaker_opens_after_threshold():
    breaker = _Breaker(threshold=2, cooldown=30, clock=lambda: 0.0)
    assert breaker.allow()
    breaker.failure()
    assert breaker.allow()
    breaker.failure()
    assert not breaker.allow()


def test_rate_limiter_rejects_when_exhausted():
    now = [0.0]
    limiter = RateLimiter(rpm=1, clock=lambda: now[0])
    assert limiter.allow()
    assert not limiter.allow()
    now[0] = 61.0
    assert limiter.allow()


def test_router_raises_rate_limited():
    router = Router(
        providers={"a": FakeProvider("a")}, chains={"default": ["a"]},
        limiter=RateLimiter(rpm=1, clock=lambda: 0.0), sleep=lambda _: None,
    )
    assert router.complete("analysis", _request()).text == "ok"
    with pytest.raises(RateLimited):
        router.complete("analysis", _request())


def test_stream_concatenates_chunks():
    router = _router([FakeProvider("a")], ["a"])
    assert "".join(router.stream("analysis", _request())) == "ab"
