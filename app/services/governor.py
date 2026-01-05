from datetime import datetime, timedelta, date
from typing import Optional
import logging

from app.config import get_settings
from app.models import Trade, GovernorCooldown


logger = logging.getLogger(__name__)


def allow_trade(session, ticker: str, mutate: bool = True) -> tuple[bool, Optional[str]]:
    settings = get_settings()
    now = datetime.utcnow()
    open_count = (
        session.query(Trade)
        .filter(Trade.status.in_(["OPEN", "PENDING"]))
        .count()
    )
    if open_count > 25:
        logger.warning("Open trade count high (%s) — restricting to fresh tickers", open_count)
    open_trade = (
        session.query(Trade)
        .filter(Trade.ticker == ticker, Trade.status.in_(["OPEN", "PENDING"]))
        .first()
    )
    if open_trade:
        return False, "Existing open trade"

    cutoff = now - timedelta(minutes=settings.cooldown_minutes)
    recent = session.query(Trade).filter(Trade.ticker == ticker, Trade.opened_at >= cutoff).count()
    if recent >= settings.max_alerts_per_ticker_per_day:
        return False, "Max alerts reached"

    cooldown = session.query(GovernorCooldown).filter(GovernorCooldown.ticker == ticker).first()
    if cooldown:
        if cooldown.locked:
            return False, "Ticker locked"
        if cooldown.as_of_date == date.today() and cooldown.alerts_today >= settings.max_alerts_per_ticker_per_day:
            return False, "Daily cap"
        if (now - cooldown.last_alert_at) < timedelta(minutes=settings.alert_cooldown_minutes):
            return False, "Cooling down"
        if not mutate:
            return True, None
        if cooldown.as_of_date != date.today():
            cooldown.alerts_today = 0
        cooldown.last_alert_at = now
        cooldown.as_of_date = date.today()
        cooldown.alerts_today = cooldown.alerts_today + 1
    else:
        if mutate:
            cooldown = GovernorCooldown(ticker=ticker, last_alert_at=now, as_of_date=date.today(), alerts_today=1)
            session.add(cooldown)
    if mutate:
        session.commit()
    return True, None
