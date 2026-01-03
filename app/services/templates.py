import os
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


def _contract_label(contract: dict, ticker: str) -> str:
    symbol = contract.get("symbol") or ticker
    exp = contract.get("expiration") or contract.get("exp") or ""
    strike = contract.get("strike")
    parts = [symbol]
    if strike is not None:
        parts.append(str(strike))
    if exp:
        parts.append(f"Exp {exp}")
    return " ".join(parts)


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


def format_trade_idea_with_options(signal: SignalCandidate, contract: dict) -> str:
    style = _alert_style()
    direction = _direction_text(signal.direction)
    contract_label = _contract_label(contract, signal.ticker)
    reasons = _reason_lines(signal.reasons or [], limit=3 if style != "deep" else None)
    entry_line = _plan_lines(signal)[0]

    if style == "short":
        parts = [
            f"🚨 TRADE IDEA — {signal.ticker} {direction}",
            reasons[0] if reasons else f"Setup: {signal.setup_name}",
            entry_line,
            f"Contract {contract_label}",
        ]
        return "\n".join(filter(None, parts))

    if style == "deep":
        details = [
            f"Timeframe: {signal.timeframe}",
            f"Regime: {signal.regime}",
            _confidence(signal),
        ]
        detail_reasons = reasons or [f"Setup: {signal.setup_name}"]
        lines = [
            f"🚨 TRADE IDEA — {signal.ticker} {direction}",
            "Reasons:",
            *detail_reasons,
            "",
            entry_line,
            f"Contract {contract_label}",
            "Plan: take partials at first target, trail toward the second target if momentum holds.",
            *details,
        ]
        return "\n".join(filter(None, lines))

    # medium
    lines = [
        f"🚨 TRADE IDEA — {signal.ticker} {direction}",
        (reasons[0] if reasons else f"Setup: {signal.setup_name}"),
    ]
    if len(reasons) > 1:
        lines.append(f"Also: {', '.join(reasons[1:])}")
    lines.extend(
        [
            entry_line,
            f"Contract {contract_label}",
            "Plan: respect the stop, scale at first target, let a runner push toward the second.",
        ]
    )
    return "\n".join(filter(None, lines))


def format_trade_idea_stock_only(signal: SignalCandidate, reason: str) -> str:
    style = _alert_style()
    direction = "LONG" if signal.direction == "bull" else "SHORT"
    reasons = _reason_lines(signal.reasons or [], limit=3 if style != "deep" else None)
    entry_line = _plan_lines(signal)[0]

    base_heading = f"🚨 TRADE IDEA — {signal.ticker} STOCK" if direction == "LONG" else f"🚨 TRADE IDEA — {signal.ticker} SHORT"
    fallback_reason = reason or "Playing stock only — options not attractive right now."

    if style == "short":
        parts = [
            base_heading,
            reasons[0] if reasons else fallback_reason,
            entry_line,
            "Playing shares (no contract selected).",
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
            "Reasons:",
            *detail_reasons,
            "",
            entry_line,
            "Plan: manage risk with the posted stop; targets outline the exit ladder.",
            *details,
        ]
        return "\n".join(filter(None, lines))

    # medium
    lines = [
        base_heading,
        (reasons[0] if reasons else fallback_reason),
    ]
    if len(reasons) > 1:
        lines.append(f"Also: {', '.join(reasons[1:])}")
    lines.extend(
        [
            entry_line,
            "Playing shares (no options contract meets criteria).",
            "Plan: respect the stop, trim at first target, trail toward the second target.",
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
            f"Filled at {entry_fill} (trigger {entry_trigger}).\n"
            f"Stop {stop} | Targets {t1} → {t2}"
        )

    if style == "deep":
        return (
            f"✅ I'M IN — {trade.ticker} {direction}\n"
            f"Trigger hit at {entry_fill} (planned {entry_trigger}).\n"
            f"Stop {stop} | Targets {t1} → {t2}\n"
            "Plan: keep stop firm until first target, then trail to protect gains."
        )

    # medium
    return (
        f"✅ I'M IN — {trade.ticker} {direction}\n"
        f"Entry filled around {entry_fill} (trigger {entry_trigger}).\n"
        f"Stop {stop} | Targets {t1} → {t2}\n"
        "Plan: trim at first target, let a runner aim for the second."
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

    if style == "short":
        return (
            f"🏁 I'M OUT — {trade.ticker} {direction}\n"
            f"{reason}. Entry {entry} → Exit {exit_price}"
        )

    if style == "deep":
        pnl = ""
        if trade.entry_fill and trade.exit_fill:
            pnl_value = (trade.exit_fill - trade.entry_fill) * (1 if trade.direction == "bull" else -1)
            pnl_pct = (pnl_value / trade.entry_fill) * 100
            pnl = f" P/L≈{pnl_value:.2f} ({pnl_pct:.2f}%)"
        return (
            f"🏁 I'M OUT — {trade.ticker} {direction}\n"
            f"{reason}.\n"
            f"Entry {entry} | Exit {exit_price} | Stop {stop} | Targets {t1} → {t2}{pnl}\n"
            "Notes: logging exit for review; tighten future plans if slippage repeats."
        )

    # medium
    return (
        f"🏁 I'M OUT — {trade.ticker} {direction}\n"
        f"{reason}.\n"
        f"Entry {entry} | Exit {exit_price} | Stop {stop} | Targets {t1} → {t2}"
    )


# Backward-compatible aliases
trade_idea_with_options = format_trade_idea_with_options
trade_idea_stock_only = format_trade_idea_stock_only
im_in = format_im_in
im_out = format_im_out
