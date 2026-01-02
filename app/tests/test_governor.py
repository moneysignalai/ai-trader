from datetime import datetime, timedelta
from app.services.governor import allow_trade
from app.services.trade_state import create_trade, STATE_WAITING
from app.services.setups.base import SignalCandidate


class DummySignal(SignalCandidate):
    pass


def test_governor_blocks_existing(session_with_db):
    signal = SignalCandidate(
        ticker="SPY",
        timeframe="day",
        direction="bull",
        setup_name="test",
        entry_trigger=1,
        stop=0.5,
        targets=[2, 3],
        reasons=[],
        features={},
        regime="TREND",
    )
    create_trade(session_with_db, signal)
    allowed, reason = allow_trade(session_with_db, "SPY")
    assert not allowed
    assert reason == "Existing open trade"


def test_governor_respects_cooldown(session_with_db):
    from app.config import get_settings
    settings = get_settings()
    signal = SignalCandidate(
        ticker="QQQ",
        timeframe="day",
        direction="bull",
        setup_name="test",
        entry_trigger=1,
        stop=0.5,
        targets=[2, 3],
        reasons=[],
        features={},
        regime="TREND",
    )
    trade = create_trade(session_with_db, signal)
    trade.opened_at = datetime.utcnow() - timedelta(minutes=settings.cooldown_minutes / 2)
    session_with_db.commit()
    allowed, _ = allow_trade(session_with_db, "QQQ")
    assert not allowed
