from types import SimpleNamespace

import app.main as main
from app.services.setups.base import SignalCandidate


def test_run_scan_passes_timeframe(monkeypatch, session_with_db):
    signal = SignalCandidate(
        ticker="SPY",
        timeframe="day",
        direction="bull",
        setup_name="test",
        entry_trigger=10.0,
        stop=9.0,
        targets=[11.0, 12.0],
        reasons=[],
        features={},
        regime="TREND",
    )

    def fake_find_signal(ticker, client, min_score, return_best=False):
        return signal, SimpleNamespace(total=99)

    class DummyClient:
        def get_snapshot(self, _ticker):
            return {"last": 10.5}

        def get_options_chain_snapshot(self, _ticker):
            return {}

        def unified_snapshot_single_ticker(self, _ticker, type="stocks"):
            return None

    class DummyDecision:
        contract = None
        reason = ""
        fallback_reasons: list[str] = []

    called_timeframes: list[str] = []

    def fake_create_trade(_session, _signal, **kwargs):
        called_timeframes.append(kwargs.get("timeframe"))
        return SimpleNamespace(_was_created=False)

    monkeypatch.setattr(main, "MassiveClient", lambda: DummyClient())
    monkeypatch.setattr(main, "_find_signal_for_ticker", fake_find_signal)
    monkeypatch.setattr(main.universe_service, "latest_universe", lambda _session: ["SPY"])
    monkeypatch.setattr(main.universe_service, "contains_placeholder_tickers", lambda _tickers: False)
    monkeypatch.setattr(main.universe_service, "is_placeholder_ticker", lambda _ticker: False)
    monkeypatch.setattr(main, "allow_trade", lambda _session, _ticker, mutate=True: (True, None))
    monkeypatch.setattr(main, "select_option", lambda *args, **kwargs: DummyDecision())
    monkeypatch.setattr(main, "send_or_log", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "record_trade_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "format_trade_idea_stock_only", lambda *args, **kwargs: "message")
    monkeypatch.setattr(main, "create_trade", fake_create_trade)
    monkeypatch.setattr(main, "_within_rth", lambda: True)

    result = main.run_scan("day", session_with_db)

    assert called_timeframes == ["day"]
    assert result.get("alerts_sent") == 1
