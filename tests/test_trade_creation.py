from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Trade
from app.services.trade_state import create_trade


def test_trade_persisted_with_autoincrement_id_and_uuid():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    trade = Trade(
        ticker="AAPL",
        side="bullish",
        status="PENDING",
        opened_at=datetime.utcnow(),
    )
    session.add(trade)

    session.commit()

    assert isinstance(trade.id, int)
    assert trade.id > 0
    assert trade.trade_uuid
    session.close()


def test_create_trade_sets_setup_name_and_commits():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)

    class Signal:
        ticker = "MSFT"
        direction = "bull"
        setup_name = "trend_pullback"

    trade = create_trade(session, Signal())
    session.commit()

    assert trade.setup_name == "trend_pullback"
    assert trade.setup == "trend_pullback"
    session.close()
