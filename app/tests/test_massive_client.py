from datetime import timedelta

from app.services.massive_client import MassiveClient
from app.utils.dates import et_today_date, iso_yyyy_mm_dd


def test_get_aggregates_defaults_to_recent_window(monkeypatch):
    client = MassiveClient(base_url="https://example.com", api_key="demo")
    captured = {}

    def fake_request(method, path, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params or {}
        return {"results": [{"o": 1}]}

    monkeypatch.setattr(client, "_request", fake_request)

    today = et_today_date()
    expected_to = iso_yyyy_mm_dd(today)
    expected_from = iso_yyyy_mm_dd(today - timedelta(days=7))

    results = client.get_aggregates("SPY", timespan="minute")

    assert results == [{"o": 1}]
    assert expected_from in captured["path"]
    assert expected_to in captured["path"]
    assert "2024-01-01" not in captured["path"]
    assert captured["params"].get("limit") == 5000
    assert captured["params"].get("from") == expected_from
    assert captured["params"].get("to") == expected_to
