from app.services.trade_state import create_trade, update_trade_states
from app.services.setups.base import SignalCandidate


def _signal():
    return SignalCandidate(
        ticker="SPY",
        timeframe="day",
        direction="bull",
        setup_name="test",
        entry_trigger=10,
        stop=9,
        targets=[11, 12],
        reasons=[],
        features={},
        regime="TREND",
    )


def test_trade_persists_timeframe(session_with_db):
    sig = _signal()
    trade = create_trade(session_with_db, sig, timeframe="day")

    session_with_db.commit()

    assert trade.timeframe == "day"


def test_state_machine_flow(session_with_db):
    sig = _signal()
    trade = create_trade(session_with_db, sig)

    price_lookup = lambda _t: 10.1
    entries, exits = update_trade_states(session_with_db, price_lookup)
    assert entries
    assert entries[0].status == "OPEN"
    assert entries[0].entry_price == price_lookup(sig.ticker)

    # stop hit
    price_lookup = lambda _t: 8.5
    entries, exits = update_trade_states(session_with_db, price_lookup)
    assert exits[-1].status == "CLOSED"
    assert exits[-1].exit_reason == "stop"
