import logging
from datetime import datetime, timedelta
from typing import Callable, List, Tuple
from uuid import uuid4

from app.config import get_settings
from app.models import Trade

logger = logging.getLogger(__name__)


def _coerce_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def create_trade(
    session,
    signal,
    option_symbol: str | None = None,
    entry_price: float | None = None,
    entry_mode: str | None = None,
    timeframe: str | None = None,
) -> Trade:
    existing = (
        session.query(Trade)
        .filter(Trade.ticker == signal.ticker, Trade.status.in_(["OPEN", "PENDING"]))
        .first()
    )
    if existing:
        setattr(existing, "_was_created", False)
        return existing

    raw_setup = getattr(signal, "setup_name", None) or getattr(signal, "setup", None) or ""
    setup_name = (raw_setup or "").strip()
    if not setup_name:
        setup_name = "unknown"
        logger.warning("Signal missing setup_name; defaulting to 'unknown' for ticker=%s", signal.ticker)

    targets = getattr(signal, "targets", None) or []
    side = "bullish" if getattr(signal, "direction", "bull") == "bull" else "bearish"
    trade_status = "OPEN" if (entry_mode or "confirm") == "immediate" else "PENDING"
    resolved_entry_price = entry_price if trade_status == "OPEN" else None

    resolved_timeframe = (timeframe or getattr(signal, "timeframe", None) or "day").strip() or "day"

    trade = Trade(
        ticker=signal.ticker,
        setup=setup_name,
        setup_name=setup_name,
        side=side,
        status=trade_status,
        opened_at=datetime.utcnow(),
        timeframe=resolved_timeframe,
        entry_price=resolved_entry_price,
        entry_trigger_price=getattr(signal, "entry_trigger", None),
        stop_price=getattr(signal, "stop", None),
        target_prices=targets if isinstance(targets, list) else [],
        last_price=entry_price,
        max_favorable=0.0 if resolved_entry_price is not None else None,
        option_symbol=option_symbol,
        entry_trigger=getattr(signal, "entry_trigger", None),
        t1=targets[0] if len(targets) > 0 else None,
        t2=targets[1] if len(targets) > 1 else None,
        trade_uuid=str(uuid4()),
    )
    session.add(trade)
    session.flush()
    session.refresh(trade)
    setattr(trade, "_was_created", True)

    if trade_status == "OPEN":
        logger.info(
            "TRADE TRANSITION ticker=%s from=PENDING to=OPEN reason=immediate_entry",
            trade.ticker,
        )
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
    trades = (
        session.query(Trade)
        .filter(Trade.status.in_(["PENDING", "OPEN"]))
        .all()
    )
    evaluated_count = len(trades)
    opened_count = 0
    closed_count = 0
    skipped_missing_price = 0
    skipped_missing_trigger = 0
    for trade in trades:
        price = _coerce_float(price_lookup(trade.ticker))
        trade.last_price = price if price is not None else None

        if price is None:
            skipped_missing_price += 1
            logger.warning("No price for ticker=%s; skipping trade_state update", trade.ticker)
            continue

        if trade.status == "PENDING" and settings.entry_mode == "confirm":
            trigger = _coerce_float(trade.entry_trigger_price) or _coerce_float(trade.entry_trigger)
            if trigger is None:
                skipped_missing_trigger += 1
                logger.info(
                    "Pending trade missing trigger; trade_id=%s ticker=%s", trade.id, trade.ticker
                )
                continue
            if _target_hit(trade, price, trigger):
                trade.entry_price = price
                trade.max_favorable = 0.0
                trade.status = "OPEN"
                trade.opened_at = now
                entries.append(trade)
                opened_count += 1
                logger.info(
                    "TRADE TRANSITION ticker=%s from=PENDING to=OPEN reason=entry_confirmed",
                    trade.ticker,
                )

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
        if trade.status == "OPEN" and trade.entry_price is not None:
            if _stop_hit(trade, price):
                exit_reason = "stop"
            elif targets:
                if targets and _target_hit(trade, price, targets[0]):
                    exit_reason = "target1"
                if exit_reason is None and len(targets) > 1 and _target_hit(trade, price, targets[1]):
                    exit_reason = "target2"
            if exit_reason is None and trade.entry_price and settings.exit_max_hours_open:
                elapsed_hours = (now - trade.opened_at) / timedelta(hours=1)
                if elapsed_hours >= settings.exit_max_hours_open:
                    exit_reason = "time"
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
                        exit_reason = "trailing_stop"
                    if (trade.side or "bullish").startswith("bear") and price >= trail_level:
                        exit_reason = "trailing_stop"

        if exit_reason:
            previous_status = trade.status
            trade.status = "CLOSED"
            trade.exit_reason = exit_reason
            trade.closed_at = now
            exits.append(trade)
            closed_count += 1
            logger.info(
                "TRADE TRANSITION ticker=%s from=%s to=CLOSED reason=%s",
                trade.ticker,
                previous_status,
                exit_reason,
            )

    logger.info(
        "Trade state update summary: evaluated=%s opened=%s closed=%s skipped_missing_price=%s skipped_missing_trigger=%s",
        evaluated_count,
        opened_count,
        closed_count,
        skipped_missing_price,
        skipped_missing_trigger,
    )

    return entries, exits
