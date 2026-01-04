from app.services.bars import normalize_bar
from app.services.feature_enricher import enrich_bars


def test_normalize_short_keys():
    bar = {"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100}

    normalized = normalize_bar(bar)

    assert normalized == {
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": 1.5,
        "volume": 100,
    }


def test_normalize_full_keys_passthrough():
    bar = {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}

    normalized = normalize_bar(bar)

    assert normalized == bar


def test_normalize_accepts_long_and_short_low_keys():
    bar = {"open": 1, "high": 2, "low": 0.5, "c": 1.5, "v": 100}

    normalized = normalize_bar(bar)

    assert normalized["low"] == 0.5


def test_enrich_bars_adds_indicators():
    bars = [
        {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        {"open": 1.4, "high": 2.2, "low": 1.0, "close": 2.0, "volume": 120},
        {"open": 1.8, "high": 2.5, "low": 1.6, "close": 2.4, "volume": 150},
    ]

    enriched = enrich_bars(bars)

    assert all("vwap" in bar for bar in enriched)
    assert any(bar.get("rsi14") is not None for bar in enriched)
