from app.services.trade_state import create_trade, update_trade_states, STATE_WAITING, STATE_IN, STATE_CLOSED
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


def test_state_machine_flow(session_with_db):
    sig = _signal()
    trade = create_trade(session_with_db, sig)

    price_lookup = lambda _t: 10.1
    updated = update_trade_states(session_with_db, price_lookup)
    assert updated[0].state == STATE_IN

    # stop hit
    price_lookup = lambda _t: 8.5
    updated = update_trade_states(session_with_db, price_lookup)
    assert updated[-1].state == STATE_CLOSED
    assert updated[-1].exit_reason == "Invalidation"
