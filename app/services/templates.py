import os
from datetime import datetime
from typing import Iterable, List

from app.config import get_settings
from app.services.setups.base import SignalCandidate


def _alert_style() -> str:
    settings = get_settings()
    style = (getattr(settings, "alert_style", None) or os.getenv("ALERT_STYLE", "medium")).lower()
    return style if style in {"short", "medium", "deep"} else "medium"


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_number(value) -> str:
    if value is None:
        return "-"
    try:
        if isinstance(value, float):
            return f"{value:.2f}"
        return f"{int(value)}"
    except (TypeError, ValueError):
        return str(value)


def _format_date(expiration: str | None, expiration_iso: str | None = None) -> str:
    candidate = expiration_iso or expiration
    if not candidate:
        return "-"
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(candidate, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return str(expiration or candidate)


def _dte(expiration_iso: str | None, expiration: str | None = None) -> str:
    candidate = expiration_iso or expiration
    if not candidate:
        return "-"
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            exp_date = datetime.strptime(candidate, fmt).date()
            days = (exp_date - datetime.utcnow().date()).days
            return str(days)
        except ValueError:
            continue
    return "-"


def _reasons(reasons: Iterable[str], limit: int = 3) -> List[str]:
    filtered = [reason for reason in reasons if reason]
    return filtered[:limit] if filtered else []


def format_trade_idea_with_options(signal: SignalCandidate, contract: dict) -> str:
    _alert_style()  # retained for compatibility, but medium tone is always used
    direction = "CALLS" if signal.direction == "bull" else "PUTS"

    expiration_text = _format_date(contract.get("expiration"), contract.get("expiration_iso"))
    dte_text = _dte(contract.get("expiration_iso"), contract.get("expiration"))
    strike = _fmt_price(contract.get("strike"))
    opt_code = "C" if direction == "CALLS" else "P"

    bid = _fmt_price(contract.get("bid"))
    ask = _fmt_price(contract.get("ask"))
    mid_raw = contract.get("mid")
    if mid_raw is None and contract.get("bid") is not None and contract.get("ask") is not None:
        mid_raw = (contract.get("bid") + contract.get("ask")) / 2
    mid = _fmt_price(mid_raw)

    spread_val = contract.get("spread_pct")
    spread_val = spread_val * 100 if isinstance(spread_val, (int, float)) else None
    spread = _fmt_percent(spread_val)

    volume = contract.get("volume")
    open_interest = contract.get("open_interest")

    delta = contract.get("delta")
    delta_text = _fmt_number(delta) if delta is not None else None

    iv_raw = contract.get("iv")
    if isinstance(iv_raw, (int, float)):
        iv_raw = iv_raw * 100 if iv_raw < 2 else iv_raw
    iv_text = _fmt_percent(iv_raw) if iv_raw is not None else None

    reasons = _reasons(signal.reasons or [], limit=3)
    if not reasons:
        reasons = [signal.setup_name, "Liquidity looks tradable", "Risk defined with stop"]

    entry = _fmt_price(signal.entry_trigger)
    stop = _fmt_price(signal.stop)
    t1 = _fmt_price(signal.targets[0] if signal.targets else None)
    t2 = _fmt_price(signal.targets[1] if signal.targets and len(signal.targets) > 1 else None)

    lines = [
        f"🚨 TRADE IDEA — {signal.ticker} {direction}",
        "",
        f"Underlying: {signal.ticker} @ {_fmt_price(contract.get('underlying_price') or signal.entry_trigger)}",
        f"Contract: {expiration_text} {strike}{opt_code} (DTE: {dte_text})",
        f"Premium: {mid} mid ({bid} x {ask}) | Spread: {spread}",
    ]

    vol_line_parts = []
    if volume is not None:
        vol_line_parts.append(str(_fmt_number(volume)))
    if open_interest is not None:
        vol_line_parts.append(str(_fmt_number(open_interest)))
    if vol_line_parts:
        lines.append(f"Vol/OI: {' / '.join(vol_line_parts)}")

    if delta_text is not None or iv_text is not None:
        lines.append(f"Delta: {delta_text or '-'} | IV: {iv_text or '-'}")

    lines.extend(
        [
            "",
            f"Entry: {entry}",
            f"Stop: {stop}",
            f"Targets: {t1} → {t2}",
            "",
            "Why I like it:",
            *[f"• {reason}" for reason in reasons],
            "",
            "Waiting for trigger.",
        ]
    )

    return "\n".join(lines)


def format_trade_idea_stock_only(signal: SignalCandidate, reason: str) -> str:
    _alert_style()  # compatibility no-op
    entry = _fmt_price(signal.entry_trigger)
    stop = _fmt_price(signal.stop)
    t1 = _fmt_price(signal.targets[0] if signal.targets else None)
    t2 = _fmt_price(signal.targets[1] if signal.targets and len(signal.targets) > 1 else None)

    lines = [
        f"🚨 TRADE IDEA — {signal.ticker} (STOCK)",
        "",
        f"Entry: {entry}",
        f"Stop: {stop}",
        f"Targets: {t1} → {t2}",
        "",
        "Why stock over options:",
        "• Options premiums elevated or illiquid",
        "• Cleaner risk with shares",
        "",
        "Plan is simple: respect the stop.",
    ]

    return "\n".join(lines)


def format_im_in(trade) -> str:
    _alert_style()  # compatibility no-op
    direction = "CALLS" if trade.direction == "bull" else "PUTS"
    entry_fill = _fmt_price(getattr(trade, "entry_fill", None) or getattr(trade, "entry_trigger", None))
    stop = _fmt_price(getattr(trade, "stop", None))
    t1 = _fmt_price(getattr(trade, "t1", None))
    t2 = _fmt_price(getattr(trade, "t2", None))

    lines = [
        f"✅ I'M IN — {trade.ticker} {direction}",
        "",
        f"Entry filled: {entry_fill}",
        f"Stop: {stop}",
        f"Targets: {t1} → {t2}",
        "",
        "Staying with the plan.",
    ]

    return "\n".join(lines)


def format_im_out(trade) -> str:
    _alert_style()  # compatibility no-op
    entry_price = _fmt_price(getattr(trade, "entry_fill", None) or getattr(trade, "entry_trigger", None))
    exit_price = _fmt_price(getattr(trade, "exit_fill", None) or getattr(trade, "t2", None))
    pnl_pct = None
    if getattr(trade, "entry_fill", None) is not None and getattr(trade, "exit_fill", None) is not None:
        try:
            direction_mult = 1 if trade.direction == "bull" else -1
            pnl_pct = ((trade.exit_fill - trade.entry_fill) * direction_mult / trade.entry_fill) * 100
        except Exception:  # noqa: BLE001
            pnl_pct = None

    lines = [
        f"🏁 I'M OUT — {trade.ticker}",
        "",
        f"Entry: {entry_price}",
        f"Exit: {exit_price}",
        f"Result: {_fmt_percent(pnl_pct) if pnl_pct is not None else '-'}",
        "",
        "Trade closed. Risk managed.",
    ]

    return "\n".join(lines)


# Backward-compatible aliases
trade_idea_with_options = format_trade_idea_with_options
trade_idea_stock_only = format_trade_idea_stock_only
im_in = format_im_in
im_out = format_im_out
