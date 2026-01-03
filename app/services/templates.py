import os
from datetime import datetime
from typing import Iterable, List

from app.config import get_settings
from app.services.setups.base import SignalCandidate


_ALLOWED_STYLES = {"short", "medium", "deep"}


def _alert_style() -> str:
    settings = get_settings()
    style = (getattr(settings, "alert_style", None) or os.getenv("ALERT_STYLE", "medium")).lower()
    return style if style in _ALLOWED_STYLES else "medium"


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _direction_text(direction: str) -> str:
    return "CALLS" if direction == "bull" else "PUTS"


def _reason_lines(reasons: Iterable[str], limit: int | None = None) -> List[str]:
    lines = [reason for reason in reasons if reason]
    if limit is not None:
        lines = lines[:limit]
    return lines


def _confidence(signal: SignalCandidate) -> str:
    score = signal.features.get("score") if signal.features else None
    return f"Confidence score: {score}" if score is not None else "Confidence score: n/a"


def _plan_lines(signal: SignalCandidate) -> List[str]:
    entry = _fmt_price(signal.entry_trigger)
    stop = _fmt_price(signal.stop)
    t1 = _fmt_price(signal.targets[0] if signal.targets else None)
    t2 = _fmt_price(signal.targets[1] if signal.targets and len(signal.targets) > 1 else None)
    levels = f"Entry {entry} | Stop {stop} | Targets {t1} → {t2}"
    return [levels]


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_number(value: float | int | None) -> str:
    if value is None:
        return "-"
    try:
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _dte(expiration: str | None) -> str:
    if not expiration:
        return "-"
    try:
        exp_date = datetime.fromisoformat(str(expiration)).date()
        days = (exp_date - datetime.utcnow().date()).days
        return str(days)
    except ValueError:
        return "-"


def format_trade_idea_with_options(signal: SignalCandidate, contract: dict) -> str:
    style = _alert_style()
    direction = _direction_text(signal.direction)
    reasons = _reason_lines(signal.reasons or [], limit=4 if style != "deep" else None)
    entry_line = _plan_lines(signal)[0]

    exp = contract.get("expiration") or contract.get("exp")
    strike = contract.get("strike")
    opt_type = (contract.get("option_type") or contract.get("type") or "").upper()
    dte = _dte(exp)
    bid = _fmt_price(contract.get("bid"))
    ask = _fmt_price(contract.get("ask"))
    mid = _fmt_price(contract.get("mid"))
    spread = _fmt_pct(contract.get("spread_pct"))
    delta = _fmt_number(contract.get("delta"))

    iv_value = contract.get("iv")
    if isinstance(iv_value, (int, float)):
        iv_value = iv_value * 100 if iv_value < 2 else iv_value
    iv = _fmt_pct(iv_value) if isinstance(iv_value, (int, float)) else "-"

    volume = _fmt_number(contract.get("volume"))
    open_interest = _fmt_number(contract.get("open_interest"))
    score_line = _confidence(signal)
    status = "Trigger hit" if getattr(signal, "triggered", False) else "Waiting for trigger"

    if style == "short":
        parts = [
            f"🚨 TRADE IDEA — {signal.ticker} {direction}",
            score_line,
            entry_line,
            f"Contract: Exp {exp or '-'} | Strike {strike} | Type {opt_type} | DTE {dte}",
            f"Pricing: Mid {mid} | Bid {bid} / Ask {ask}",
            f"Reasons: {reasons[0] if reasons else signal.setup_name}",
            status,
        ]
        return "\n".join(filter(None, parts))

    if style == "deep":
        details = [
            f"Timeframe: {signal.timeframe}",
            f"Regime: {signal.regime}",
            score_line,
        ]
        detail_reasons = reasons or [f"Setup: {signal.setup_name}"]
        lines = [
            f"🚨 TRADE IDEA — {signal.ticker} {direction}",
            entry_line,
            f"Contract: Exp {exp or '-'} | Strike {strike} | Type {opt_type} | DTE {dte}",
            f"Pricing: Mid {mid} | Bid {bid} / Ask {ask} | Spread {spread}",
            f"Greeks/IV: Delta {delta} | IV {iv}",
            f"Liquidity: Volume {volume} | OI {open_interest}",
            "Reasons:",
            *[f"- {reason}" for reason in detail_reasons],
            status,
            "Plan: respect the stop, scale out toward targets, and reassess if volume fades.",
            *details,
        ]
        return "\n".join(filter(None, lines))

    # medium
    reason_lines = [f"- {reason}" for reason in reasons] if reasons else [f"- Setup: {signal.setup_name}"]
    lines = [
        f"🚨 TRADE IDEA — {signal.ticker} {direction}",
        score_line,
        entry_line,
        f"Contract: Exp {exp or '-'} | Strike {strike} | Type {opt_type} | DTE {dte}",
        f"Pricing: Mid {mid} | Bid {bid} / Ask {ask} | Spread {spread}",
        f"Greeks/IV: Delta {delta} | IV {iv}",
        f"Liquidity: Volume {volume} | OI {open_interest}",
        "Reasons:",
        *reason_lines,
        status,
    ]
    return "\n".join(filter(None, lines))


def format_trade_idea_stock_only(signal: SignalCandidate, reason: str) -> str:
    style = _alert_style()
    direction = "LONG" if signal.direction == "bull" else "SHORT"
    reasons = _reason_lines(signal.reasons or [], limit=4 if style != "deep" else None)
    entry_line = _plan_lines(signal)[0]

    base_heading = f"🚨 TRADE IDEA — {signal.ticker} STOCK" if direction == "LONG" else f"🚨 TRADE IDEA — {signal.ticker} SHORT"
    fallback_reason = reason or "Playing stock only — options not attractive right now."

    score_line = _confidence(signal)
    status = "Trigger hit" if getattr(signal, "triggered", False) else "Waiting for trigger"

    if style == "short":
        parts = [
            base_heading,
            score_line,
            entry_line,
            reasons[0] if reasons else fallback_reason,
            status,
        ]
        return "\n".join(filter(None, parts))

    if style == "deep":
        details = [
            f"Timeframe: {signal.timeframe}",
            f"Regime: {signal.regime}",
            _confidence(signal),
        ]
        detail_reasons = reasons if reasons else [fallback_reason]
        lines = [
            base_heading,
            score_line,
            "Reasons:",
            *detail_reasons,
            "",
            entry_line,
            f"Plan: manage risk with the posted stop; targets outline the exit ladder. {status}.",
            *details,
        ]
        return "\n".join(filter(None, lines))

    # medium
    lines = [
        base_heading,
        score_line,
        entry_line,
        (reasons[0] if reasons else fallback_reason),
    ]
    if len(reasons) > 1:
        lines.append(f"Also: {', '.join(reasons[1:])}")
    lines.extend(
        [
            "Plan: respect the stop, trim at first target, trail toward the second target.",
            status,
        ]
    )
    return "\n".join(filter(None, lines))


def format_im_in(trade) -> str:
    style = _alert_style()
    direction = _direction_text(trade.direction)
    entry_fill = _fmt_price(trade.entry_fill or trade.entry_trigger)
    entry_trigger = _fmt_price(trade.entry_trigger)
    stop = _fmt_price(trade.stop)
    t1 = _fmt_price(trade.t1)
    t2 = _fmt_price(trade.t2)

    if style == "short":
        return (
            f"✅ I'M IN — {trade.ticker} {direction}\n"
            f"Trigger hit at {entry_fill} (plan {entry_trigger}).\n"
            f"Risk map: Stop {stop} | Targets {t1} → {t2}"
        )

    if style == "deep":
        return (
            f"✅ I'M IN — {trade.ticker} {direction}\n"
            f"Trigger confirmed at {entry_fill} (planned {entry_trigger}).\n"
            f"Risk map: Stop {stop} | Targets {t1} → {t2}\n"
            "Discipline: keep stop firm until first target, then trail to lock gains."
        )

    # medium
    return (
        f"✅ I'M IN — {trade.ticker} {direction}\n"
        f"Trigger hit at {entry_fill} (plan {entry_trigger}).\n"
        f"Risk map: Stop {stop} | Targets {t1} → {t2}\n"
        "Plan: trim at first target, let a runner aim for the second with stop discipline."
    )


def format_im_out(trade) -> str:
    style = _alert_style()
    direction = _direction_text(trade.direction)
    entry = _fmt_price(trade.entry_fill or trade.entry_trigger)
    exit_price = _fmt_price(trade.exit_fill or trade.t2)
    stop = _fmt_price(trade.stop)
    t1 = _fmt_price(trade.t1)
    t2 = _fmt_price(trade.t2)
    reason = trade.exit_reason or "Plan closed"

    pnl_text = ""
    if trade.entry_fill and trade.exit_fill:
        pnl_value = (trade.exit_fill - trade.entry_fill) * (1 if trade.direction == "bull" else -1)
        pnl_pct = (pnl_value / trade.entry_fill) * 100
        pnl_text = f" P/L≈{pnl_value:.2f} ({pnl_pct:.2f}%)"

    if style == "short":
        return (
            f"🏁 I'M OUT — {trade.ticker} {direction}\n"
            f"{reason}. Entry {entry} → Exit {exit_price}"
        )

    if style == "deep":
        return (
            f"🏁 I'M OUT — {trade.ticker} {direction}\n"
            f"{reason}.\n"
            f"Entry {entry} | Exit {exit_price} | Stop {stop} | Targets {t1} → {t2}{pnl_text}\n"
            "Notes: logging exit for review; tighten future plans if slippage repeats."
        )

    # medium
    return (
        f"🏁 I'M OUT — {trade.ticker} {direction}\n"
        f"{reason}.\n"
        f"Entry {entry} | Exit {exit_price} | Stop {stop} | Targets {t1} → {t2}{pnl_text}"
    )


# Backward-compatible aliases
trade_idea_with_options = format_trade_idea_with_options
trade_idea_stock_only = format_trade_idea_stock_only
im_in = format_im_in
im_out = format_im_out
