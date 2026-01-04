import re
from datetime import datetime, timedelta

from app.services.setups.base import SignalCandidate
from app.services.templates import (
    format_im_in,
    format_im_out,
    format_trade_idea_stock_only,
    format_trade_idea_with_options,
)
from app.utils.dates import ET, format_mmddyyyy

ALERT_TIMESTAMP_RE = re.compile(r"\b\d{2}-\d{2}-\d{4} \d{2}:\d{2} (AM|PM) ET\b")
ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T")
SECONDS_RE = re.compile(r":\d{2}:\d{2}")
MICRO_IN_TIMESTAMP_RE = re.compile(r"Timestamp:.*\.\d+")


def _assert_alert_format(text: str):
    assert ALERT_TIMESTAMP_RE.search(text)
    assert not ISO_RE.search(text)
    assert not SECONDS_RE.search(text)
    assert not MICRO_IN_TIMESTAMP_RE.search(text)


def _sample_signal():
    return SignalCandidate(
        ticker="NVDA",
        timeframe="5m",
        direction="bull",
        setup_name="trend_pullback",
        entry_trigger=118.5,
        stop=116.4,
        targets=[121.0, 124.5],
        reasons=["Reason one", "Reason two"],
        features={},
        regime="rth",
        created_at=datetime.now(ET),
    )


def _sample_contract():
    expiration_date = datetime.now(ET).date() + timedelta(days=7)
    iso_date = expiration_date.strftime("%Y-%m-%d")
    return {
        "expiration": None,
        "expiration_iso": iso_date,
        "strike": 100.0,
        "bid": 2.35,
        "ask": 2.55,
        "mid": 2.45,
        "spread_pct": 0.082,
        "volume": 12500,
        "open_interest": 68420,
        "delta": 0.55,
        "underlying_price": 118.5,
    }


def _sample_trade(direction="bull"):
    class Dummy:
        pass

    trade = Dummy()
    trade.ticker = "AMD"
    trade.direction = direction
    trade.entry_fill = 154.3
    trade.entry_trigger = 154.2
    trade.stop = 150.8
    trade.t1 = 158.0
    trade.t2 = 162.5
    trade.exit_fill = 158.0
    return trade


def test_trade_idea_with_options_includes_et_timestamp_and_mmddyyyy_date():
    message = format_trade_idea_with_options(_sample_signal(), _sample_contract())
    _assert_alert_format(message)
    assert format_mmddyyyy(datetime.now(ET).date())[:2] in message


def test_trade_idea_stock_only_includes_et_timestamp():
    message = format_trade_idea_stock_only(_sample_signal(), "Because")
    _assert_alert_format(message)


def test_im_in_includes_et_timestamp():
    message = format_im_in(_sample_trade())
    _assert_alert_format(message)


def test_im_out_includes_et_timestamp():
    message = format_im_out(_sample_trade())
    _assert_alert_format(message)
