from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.services.setups.base import SignalCandidate
from app.services.templates import (
    format_im_in,
    format_im_out,
    format_trade_idea_stock_only,
    format_trade_idea_with_options,
)


@pytest.fixture
def sample_signal():
    return SignalCandidate(
        ticker="TEST",
        timeframe="day",
        direction="bull",
        setup_name="trend_pullback",
        entry_trigger=100.0,
        stop=98.5,
        targets=[103.0, 106.0],
        reasons=["Strong volume", "VWAP reclaim"],
        features={"score": 88},
        regime="bullish",
    )


@pytest.fixture
def sample_trade():
    return SimpleNamespace(
        ticker="TEST",
        direction="bull",
        entry_trigger=100.0,
        entry_fill=100.2,
        stop=98.5,
        t1=103.0,
        t2=106.0,
        exit_fill=104.0,
        exit_reason="Target hit",
    )


@pytest.mark.parametrize("style", ["short", "medium", "deep"])
def test_templates_plain_text(monkeypatch, sample_signal, sample_trade, style):
    monkeypatch.setenv("ALERT_STYLE", style)
    get_settings.cache_clear()

    outputs = [
        format_trade_idea_with_options(sample_signal, {"symbol": "TEST123", "expiration": "2024-12-20"}),
        format_trade_idea_stock_only(sample_signal, "Options unavailable"),
        format_im_in(sample_trade),
        format_im_out(sample_trade),
    ]

    for text in outputs:
        assert isinstance(text, str)
        assert "**" not in text
        assert len(text) > 0


def test_readme_has_no_placeholders():
    content = Path("README.md").read_text()
    assert "..." not in content


def test_medium_option_template_includes_key_fields(monkeypatch, sample_signal):
    monkeypatch.setenv("ALERT_STYLE", "medium")
    get_settings.cache_clear()

    contract = {
        "symbol": "TEST123",
        "expiration": "2024-12-20",
        "strike": 100,
        "option_type": "call",
        "bid": 1.0,
        "ask": 1.2,
        "mid": 1.1,
        "spread_pct": ((1.2 - 1.0) / 1.1) * 100,
        "delta": 0.5,
        "iv": 0.45,
        "volume": 5000,
        "open_interest": 20000,
    }

    message = format_trade_idea_with_options(sample_signal, contract)

    assert isinstance(message, str)
    assert "Entry" in message
    assert "Stop" in message
    assert "Targets" in message
    assert "Bid" in message and "Ask" in message
    assert "Exp" in message and "Strike" in message
