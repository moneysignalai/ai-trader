from datetime import datetime, timedelta
from typing import Optional
from app.config import get_settings
from app.models import Trade


def allow_trade(session, ticker: str) -> tuple[bool, Optional[str]]:
    settings = get_settings()
    now = datetime.utcnow()
    # one open trade per ticker
    existing = session.query(Trade).filter(lambda t: t.ticker == ticker and t.state != "CLOSED").all()
    if existing:
        return False, "Existing open trade"
    cutoff = now - timedelta(minutes=settings.cooldown_minutes)
    recent = session.query(Trade).filter(lambda t: t.ticker == ticker and t.opened_at >= cutoff).count()
    if recent >= settings.max_alerts_per_ticker_per_day:
        return False, "Max alerts reached"
    return True, None
