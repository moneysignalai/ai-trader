from datetime import datetime
from typing import List
from app.models import Trade

STATE_WAITING = "WAITING_FOR_ENTRY"
STATE_IN = "IN_POSITION"
STATE_MANAGING = "MANAGING_POSITION"
STATE_CLOSED = "CLOSED"


def create_trade(session, signal, option_symbol: str | None = None) -> Trade:
    trade = Trade(
        ticker=signal.ticker,
        timeframe=signal.timeframe,
        setup_name=signal.setup_name,
        direction=signal.direction,
        state=STATE_WAITING,
        entry_trigger=signal.entry_trigger,
        stop=signal.stop,
        t1=signal.targets[0],
        t2=signal.targets[1],
        option_symbol=option_symbol,
        telegram_msg_ids_json={},
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


def update_trade_states(session, price_lookup: callable) -> List[Trade]:
    updated = []
    trades = session.query(Trade).filter(lambda t: t.state != STATE_CLOSED).all()
    for trade in trades:
        price = price_lookup(trade.ticker)
        if trade.state == STATE_WAITING:
            if (trade.direction == "bull" and price >= trade.entry_trigger) or (
                trade.direction == "bear" and price <= trade.entry_trigger
            ):
                trade.state = STATE_IN
                trade.entry_fill = price
                trade.entered_at = datetime.utcnow()
                updated.append(trade)
        elif trade.state == STATE_IN:
            if (trade.direction == "bull" and price <= trade.stop) or (
                trade.direction == "bear" and price >= trade.stop
            ):
                trade.state = STATE_CLOSED
                trade.exit_reason = "Invalidation"
                trade.exited_at = datetime.utcnow()
                updated.append(trade)
            elif (trade.direction == "bull" and price >= trade.t2) or (
                trade.direction == "bear" and price <= trade.t2
            ):
                trade.state = STATE_CLOSED
                trade.exit_reason = "Target hit"
                trade.exited_at = datetime.utcnow()
                updated.append(trade)
    session.commit()
    return updated
