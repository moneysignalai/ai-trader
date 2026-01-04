import re
from pathlib import Path
from types import SimpleNamespace

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_templates_plain_text(sample_signal, sample_trade):
    outputs = [
        format_trade_idea_with_options(
            sample_signal,
            {"symbol": "TEST123", "expiration": "12-20-2024", "underlying_price": 100.0},
        ),
        format_trade_idea_stock_only(sample_signal, "Options unavailable"),
        format_im_in(sample_trade),
        format_im_out(sample_trade),
    ]

    for text in outputs:
        assert isinstance(text, str)
        assert len(text) > 0
        assert "YYYY-MM-DD" not in text


def test_readme_has_no_placeholders():
    content = Path("README.md").read_text()
    assert "..." not in content


def test_option_template_includes_pricing_lines(sample_signal):
    contract = {
        "symbol": "TEST123",
        "expiration": "12-20-2024",
        "expiration_iso": "2024-12-20",
        "strike": 100,
        "option_type": "call",
        "bid": 1.0,
        "ask": 1.2,
        "mid": 1.1,
        "spread_pct": (1.2 - 1.0) / 1.1,
        "delta": 0.5,
        "iv": 0.45,
        "volume": 5000,
        "open_interest": 20000,
        "underlying_price": 99.5,
    }

    message = format_trade_idea_with_options(sample_signal, contract)

    assert isinstance(message, str)
    assert "Bid/Ask:" in message
    assert "Spread:" in message
    assert "OI/Vol:" in message
    assert "12-20-2024" in message


def test_alerts_do_not_show_iso_dates(sample_signal, sample_trade):
    contract = {"symbol": "TEST123", "expiration": "01-09-2026", "strike": 100, "option_type": "call"}
    outputs = [
        format_trade_idea_with_options(sample_signal, contract),
        format_trade_idea_stock_only(sample_signal, "Options unavailable"),
        format_im_in(sample_trade),
        format_im_out(sample_trade),
    ]

    for text in outputs:
        assert "2024-" not in text
        assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", text) is None


def test_alert_dates_normalized_to_mmddyyyy(sample_signal):
    contract = {"symbol": "TEST123", "expiration": "2026-01-09", "strike": 100, "option_type": "call"}
    message = format_trade_idea_with_options(sample_signal, contract)

    assert "01-09-2026" in message
    assert "2026-01-09" not in message
    assert "09-01-2026" not in message
    assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", message) is None
