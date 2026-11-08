from app import tracing


def test_span_records_tree():
    tracing.new_trace()
    with tracing.span("outer", kind="stage"):
        with tracing.span("inner", kind="tool"):
            pass
    trace_id = tracing.current_trace()
    tree = tracing.list_trace(trace_id)
    assert tree["count"] == 2
    assert len(tree["roots"]) == 1
    root = tree["roots"][0]
    assert root["name"] == "outer"
    assert root["children"][0]["name"] == "inner"
    assert root["duration_ms"] >= 0


def test_error_span_keeps_error_attributes():
    tracing.new_trace()
    try:
        with tracing.span("boom"):
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    tree = tracing.list_trace(tracing.current_trace())
    names = [node["name"] for node in tree["roots"]]
    assert "boom" in names


def test_record_without_trace_generates_one():
    tracing.new_trace()
    tracing.record("direct")
    assert tracing.current_trace()
