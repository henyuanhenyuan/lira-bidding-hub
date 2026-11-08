from app import handoff


def test_record_and_count():
    handoff.record("run-1", 1, handoff.Handoff("steward", "analysis", "ready"))
    assert handoff.count("run-1") == 1
    assert handoff.allowed("run-1") is True


def test_cap_at_max_handoffs():
    for index in range(handoff.MAX_HANDOFFS):
        handoff.record(
            "run-2", index + 1,
            handoff.Handoff("steward", "analysis", f"step-{index}"),
        )
    assert handoff.allowed("run-2") is False


def test_chain_returns_messages():
    handoff.record(
        "run-3", 1,
        handoff.Handoff("steward", "risk", "check_margin", {"price": 99}),
    )
    chain = handoff.chain("run-3")
    assert chain[0]["name"] == "steward->risk"
    assert chain[0]["output"] == "check_margin"
