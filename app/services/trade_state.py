from datetime import datetime, timedelta
from typing import Callable, List, Tuple

from app.config import get_settings
from app.models import Trade


def create_trade(
    session,
    signal,
    option_symbol: str | None = None,
    entry_price: float | None = None,
    entry_mode: str | None = None,
) -> Trade:
    existing = (
        session.query(Trade)
        .filter(Trade.ticker == signal.ticker, Trade.status == "OPEN")
        .first()
    )
    if existing:
        return existing

    targets = getattr(signal, "targets", None) or []
    side = "bullish" if getattr(signal, "direction", "bull") == "bull" else "bearish"
    trade = Trade(
        ticker=signal.ticker,
        setup=getattr(signal, "setup_name", None),
        side=side,
        status="OPEN",
        opened_at=datetime.utcnow(),
        entry_price=entry_price if (entry_mode or "confirm") == "immediate" else None,
        entry_trigger_price=getattr(signal, "entry_trigger", None),
        stop_price=getattr(signal, "stop", None),
        target_prices=targets if isinstance(targets, list) else [],
        last_price=entry_price,
        max_favorable=0.0,
        option_symbol=option_symbol,
        entry_trigger=getattr(signal, "entry_trigger", None),
        t1=targets[0] if len(targets) > 0 else None,
        t2=targets[1] if len(targets) > 1 else None,
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


def _risk_amount(trade: Trade) -> float | None:
    if trade.entry_price is None or trade.stop_price is None:
        return None
    if (trade.side or "bullish").startswith("bull"):
        return float(trade.entry_price) - float(trade.stop_price)
    return float(trade.stop_price) - float(trade.entry_price)


def _favorable_move(trade: Trade, price: float) -> float | None:
    if trade.entry_price is None:
        return None
    if (trade.side or "bullish").startswith("bull"):
        return float(price) - float(trade.entry_price)
    return float(trade.entry_price) - float(price)


def _target_hit(trade: Trade, price: float, target: float) -> bool:
    if (trade.side or "bullish").startswith("bull"):
        return price >= target
    return price <= target


def _stop_hit(trade: Trade, price: float) -> bool:
    if trade.stop_price is None:
        return False
    if (trade.side or "bullish").startswith("bull"):
        return price <= trade.stop_price
    return price >= trade.stop_price


def update_trade_states(
    session, price_lookup: Callable[[str], float], settings=None
) -> Tuple[List[Trade], List[Trade]]:
    settings = settings or get_settings()
    entries: List[Trade] = []
    exits: List[Trade] = []
    now = datetime.utcnow()
    trades = session.query(Trade).filter(Trade.status == "OPEN").all()
    for trade in trades:
        price = price_lookup(trade.ticker)
        trade.last_price = price

        if trade.entry_price is None and settings.entry_mode == "confirm":
            trigger = trade.entry_trigger_price or trade.entry_trigger
            if trigger is not None:
                if _target_hit(trade, price, trigger):
                    trade.entry_price = price
                    trade.max_favorable = 0.0
                    entries.append(trade)

        risk = _risk_amount(trade)
        fallback_targets: list[float] = []
        if (trade.target_prices is None or not trade.target_prices) and risk is not None and trade.entry_price is not None:
            direction_mult = 1 if (trade.side or "bullish").startswith("bull") else -1
            base = float(trade.entry_price)
            fallback_targets = [
                base + direction_mult * risk * settings.exit_target_r_mult_1,
                base + direction_mult * risk * settings.exit_target_r_mult_2,
            ]
        targets = trade.target_prices or fallback_targets
        favorable = _favorable_move(trade, price)
        if favorable is not None and (trade.max_favorable is None or favorable > trade.max_favorable):
            trade.max_favorable = favorable

        exit_reason: str | None = None
        if trade.entry_price is not None:
            if _stop_hit(trade, price):
                exit_reason = "Stop-loss hit"
            elif targets:
                if targets and _target_hit(trade, price, targets[0]):
                    exit_reason = "Target 1 hit"
                if exit_reason is None and len(targets) > 1 and _target_hit(trade, price, targets[1]):
                    exit_reason = "Target 2 hit"
            if exit_reason is None and trade.entry_price and settings.exit_max_hours_open:
                elapsed_hours = (now - trade.opened_at) / timedelta(hours=1)
                if elapsed_hours >= settings.exit_max_hours_open:
                    exit_reason = "Time-based exit"
            if exit_reason is None and risk and favorable is not None:
                if favorable >= settings.exit_trail_after_r * risk:
                    keep_pct = 1 - settings.exit_trail_pct
                    if keep_pct < 0:
                        keep_pct = 0
                    trail_level = (
                        trade.entry_price
                        + favorable * keep_pct
                        if (trade.side or "bullish").startswith("bull")
                        else trade.entry_price - favorable * keep_pct
                    )
                    if (trade.side or "bullish").startswith("bull") and price <= trail_level:
                        exit_reason = "Trailing stop"
                    if (trade.side or "bullish").startswith("bear") and price >= trail_level:
                        exit_reason = "Trailing stop"

        if exit_reason:
            trade.status = "CLOSED"
            trade.exit_reason = exit_reason
            trade.closed_at = now
            exits.append(trade)

    session.commit()
    return entries, exits
