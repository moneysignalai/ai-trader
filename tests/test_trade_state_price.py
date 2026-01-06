from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Trade
from app.services.trade_state import update_trade_states


def test_update_trade_states_skips_missing_price():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    trade = Trade(
        ticker="AAPL",
        side="bullish",
        status="OPEN",
        opened_at=datetime.utcnow(),
        entry_price=100.0,
        stop_price=95.0,
        stop=95.0,
    )
    session.add(trade)
    session.commit()

    def price_lookup(_):
        return None

    settings = SimpleNamespace(
        entry_mode="confirm",
        exit_target_r_mult_1=1.0,
        exit_target_r_mult_2=2.0,
        exit_max_hours_open=None,
        exit_trail_after_r=1.0,
        exit_trail_pct=0.1,
    )

    entries, exits = update_trade_states(session, price_lookup, settings=settings)

    assert entries == []
    assert exits == []

    session.refresh(trade)
    assert trade.status == "OPEN"
    assert trade.last_price is None

    session.close()
