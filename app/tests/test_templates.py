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
