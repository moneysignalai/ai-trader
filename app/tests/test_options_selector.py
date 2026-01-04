import json
from datetime import timedelta
from pathlib import Path

from app.services.options_selector import select_option
from app.services.setups.base import SignalCandidate
from app.utils.dates import et_today_date


FIXTURE = Path(__file__).parent / "fixtures" / "sample_chain_snapshot.json"


def _signal(timeframe="day"):
    from app.config import get_settings

    settings = get_settings()
    return SignalCandidate(
        ticker="SPY",
        timeframe=timeframe,
        direction="bull",
        setup_name="test",
        entry_trigger=100,
        stop=99,
        targets=[101, 102],
        reasons=["test"],
        features={"score": settings.options_only_if_score_at_least + 5},
        regime="TREND",
    )


def test_select_option_picks_liquid():
    chain = json.loads(FIXTURE.read_text())
    soon = (et_today_date() + timedelta(days=10)).isoformat()
    for leg in chain["results"]:
        leg["expiration_iso"] = soon
        leg["expiration"] = soon
    decision = select_option(_signal("day"), chain, underlying_price=100)
    assert decision.contract
    assert decision.contract["symbol"] == "TESTC1"


def test_rejects_if_no_liquidity():
    chain = json.loads(FIXTURE.read_text())
    soon = (et_today_date() + timedelta(days=10)).isoformat()
    for c in chain["results"]:
        c["expiration_iso"] = soon
        c["expiration"] = soon
    # zero out liquidity
    for c in chain["results"]:
        c["open_interest"] = 0
        c["volume"] = 0
    decision = select_option(_signal("day"), chain, underlying_price=100)
    assert decision.contract is None
    assert "expensive" in decision.reason or "illiquid" in decision.reason.lower()


def test_rejects_if_score_below_threshold():
    chain = json.loads(FIXTURE.read_text())
    soon = (et_today_date() + timedelta(days=10)).isoformat()
    for leg in chain.get("results", []):
        leg["expiration_iso"] = soon
        leg["expiration"] = soon

    from app.config import get_settings

    settings = get_settings()
    original_threshold = settings.options_only_if_score_at_least
    settings.options_only_if_score_at_least = 80
    try:
        signal = _signal("day")
        signal.features["score"] = 70
        decision = select_option(signal, chain, underlying_price=100)
        assert decision.contract is None
        assert decision.reason == "Score below options threshold"
    finally:
        settings.options_only_if_score_at_least = original_threshold
