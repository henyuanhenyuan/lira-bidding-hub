from app import db, metrics


def test_summary_reports_percentiles_and_models():
    for latency in (10, 20, 30, 400):
        metrics.record(
            "attribution", model="qwen-plus", ok=True, latency_ms=latency,
            prompt_tokens=100, completion_tokens=50, provider="openai",
            prompt_name="analysis", prompt_version="analysis-v1",
        )
    metrics.record("critic", model="qwen3:14b", ok=False, fallback=True)

    with db.get_db() as conn:
        summary = metrics.summary(conn, hours=24)

    assert summary["p50_latency_ms"] is not None
    assert summary["p95_latency_ms"] is not None
    assert summary["p99_latency_ms"] is not None
    assert summary["p50_latency_ms"] <= summary["p95_latency_ms"]
    models = {row["model"]: row for row in summary["by_model"]}
    assert models["qwen-plus"]["calls"] == 4
    assert models["qwen-plus"]["tokens"] == 600
    assert models["qwen3:14b"]["fallback"] == 1


def test_fallback_rate():
    metrics.record("attribution", model="m", ok=False, fallback=True)
    metrics.record("attribution", model="m", ok=True)
    with db.get_db() as conn:
        summary = metrics.summary(conn, hours=24)
    assert summary["fallback_rate"] == 0.5
