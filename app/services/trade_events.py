from datetime import datetime
from typing import Any, Dict

from app.models import TradeEvent
from app.utils.dates import format_et_timestamp


def record_trade_event(
    session,
    ticker: str,
    instrument_type: str,
    side: str,
    payload: Dict[str, Any],
) -> TradeEvent:
    event = TradeEvent(
        ticker=ticker,
        instrument_type=instrument_type.upper(),
        side=side,
        payload_json=payload,
        created_at_utc=datetime.utcnow(),
        created_at_et_text=format_et_timestamp(),
    )
    session.add(event)
    return event
