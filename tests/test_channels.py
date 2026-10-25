import pytest

from app.channels import get_adapter
from app.channels import api as api_channel
from app.channels import yingdao as yingdao_channel


def test_manual_dispatch_is_pending():
    result = get_adapter("manual").dispatch({"id": "task-1", "target_id": "sku-1"})
    assert result.status == "pending"
    assert "人工" in result.detail or "文件" in result.detail


def test_yingdao_writes_work_order(tmp_path):
    adapter = yingdao_channel.YingdaoAdapter(outbox=tmp_path)
    result = adapter.dispatch({"id": "task-1", "target_id": "sku-1"})
    assert result.status == "pending"
    assert result.external_ref == "task-1.json"
    payload = (tmp_path / "task-1.json").read_text(encoding="utf-8")
    assert "sku-1" in payload
    assert "task-1" in payload


def test_api_skipped_without_url():
    result = api_channel.ApiAdapter(url="").dispatch({"id": "t1", "target_id": "x"})
    assert result.status == "skipped"


def test_api_parses_snapshot(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "snapshots": [
                    {
                        "target_id": "x",
                        "ts": "2026-10-25T00:00:00+00:00",
                        "collector": "api",
                        "source_tier": 1,
                        "observation": {"list_price": 99.0},
                    }
                ]
            }

    monkeypatch.setattr(api_channel.httpx, "get", lambda *a, **k: FakeResponse())
    adapter = api_channel.ApiAdapter(url="http://example.test/feed")
    result = adapter.dispatch({"id": "t1", "target_id": "x"})
    assert result.status == "done"
    assert len(result.observations) == 1
    assert result.observations[0].observation.list_price == 99.0


def test_unknown_channel_rejected():
    with pytest.raises(ValueError):
        get_adapter("selenium")
