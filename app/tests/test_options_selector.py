import json
from pathlib import Path
from app.services.options_selector import select_option
from app.services.setups.base import SignalCandidate


FIXTURE = Path(__file__).parent / "fixtures" / "sample_chain_snapshot.json"


def _signal(timeframe="day"):
    return SignalCandidate(
        ticker="SPY",
        timeframe=timeframe,
        direction="bull",
        setup_name="test",
        entry_trigger=100,
        stop=99,
        targets=[101, 102],
        reasons=["test"],
        features={},
        regime="TREND",
    )


def test_select_option_picks_liquid():
    chain = json.loads(FIXTURE.read_text())
    decision = select_option(_signal("day"), chain, underlying_price=100)
    assert decision.contract
    assert decision.contract["symbol"] == "TESTC1"


def test_rejects_if_no_liquidity():
    chain = json.loads(FIXTURE.read_text())
    # zero out liquidity
    for c in chain["results"]:
        c["open_interest"] = 0
        c["volume"] = 0
    decision = select_option(_signal("day"), chain, underlying_price=100)
    assert decision.contract is None
    assert "expensive" in decision.reason or "illiquid" in decision.reason.lower()
