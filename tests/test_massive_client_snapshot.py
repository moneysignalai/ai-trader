import pytest

from app.services.massive_client import MassiveClient


def test_unified_snapshot_single_ticker_uses_exact_ticker_param(monkeypatch):
    client = MassiveClient(base_url="http://example.com", api_key="test-key")
    captured = {}

    def fake_request(method, path, params=None, log_errors=True):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        return {"results": [{"ticker": "ABC", "type": "stocks"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.unified_snapshot_single_ticker("ABC", type="stocks")

    assert result == {"ticker": "ABC", "type": "stocks"}
    assert captured["path"] == "/v3/snapshot"
    assert captured["params"] == {"ticker": "ABC", "type": "stocks", "limit": 1}


def test_massive_stock_snapshot_price_calls_unified_snapshot(monkeypatch):
    client = MassiveClient(base_url="http://example.com", api_key="test-key")
    calls: dict = {}

    def fake_unified(ticker, type="stocks"):
        calls["unified"] = (ticker, type)
        return {"last": 42}

    def fake_price(snapshot):
        calls["price_snapshot"] = snapshot
        return 101.5

    monkeypatch.setattr(client, "unified_snapshot_single_ticker", fake_unified)
    monkeypatch.setattr(client, "unified_snapshot_price", fake_price)

    price = client.massive_stock_snapshot_price("QBTS")

    assert price == 101.5
    assert calls["unified"] == ("QBTS", "stocks")
    assert calls["price_snapshot"] == {"last": 42}
