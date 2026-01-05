"""Legacy-compatible wrappers for alert rendering.

These functions build payloads and delegate to ``app.alerts.renderer`` so alerts
stay consistent across the stack.
"""

from __future__ import annotations

import os
from typing import Iterable, List

from app.alerts.renderer import (
    render_in_alert,
    render_option_alert,
    render_out_alert,
    render_stock_alert,
)
from app.config import get_settings
from app.services.setups.base import SignalCandidate


def _alert_style() -> str:
    settings = get_settings()
    style = (getattr(settings, "alert_style", None) or os.getenv("ALERT_STYLE", "medium")).lower()
    return style if style in {"short", "medium", "deep"} else "medium"


def _alert_mode() -> str:
    settings = get_settings()
    return (getattr(settings, "alert_mode", "ideas") or "ideas").lower()


def _fmt_price(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _market_context(setup_name: str | None) -> str:
    if not setup_name:
        return "setup"
    lowered = setup_name.lower()
    for keyword in ("breakout", "reclaim", "continuation", "pullback"):
        if keyword in lowered:
            return keyword
    return setup_name


def _reasons_list(reasons: Iterable[str] | str | None, default: List[str]) -> List[str]:
    if reasons is None:
        return default
    if isinstance(reasons, str):
        return [reasons]
    cleaned = [reason for reason in reasons if reason]
    return cleaned or default


def format_trade_idea_with_options(signal: SignalCandidate, contract: dict) -> str:
    _alert_style()  # retained for compatibility
    _alert_mode()  # retained for compatibility
    score_raw = None
    if isinstance(signal.features, dict):
        score_raw = signal.features.get("score")
    try:
        confidence = round(float(score_raw) / 10, 1) if score_raw is not None else 7.5
    except (TypeError, ValueError):
        confidence = 7.5

    payload = {
        "ticker": signal.ticker,
        "bias": "Bullish" if signal.direction == "bull" else "Bearish",
        "setup": _market_context(signal.setup_name),
        "confidence": confidence,
        "underlying_price": _fmt_price(getattr(signal, "entry_trigger", None)),
        "contract": contract,
        "plan": {
            "entry": _fmt_price(getattr(signal, "entry_trigger", None)),
            "stop": _fmt_price(getattr(signal, "stop", None)),
            "targets": [
                _fmt_price(signal.targets[0]) if signal.targets else None,
                _fmt_price(signal.targets[1]) if signal.targets and len(signal.targets) > 1 else None,
            ],
            "notes": "Watch volume and respect stops.",
        },
    }
    return render_option_alert(payload)


def format_trade_idea_stock_only(signal: SignalCandidate, reason: str | Iterable[str]) -> str:
    _alert_style()  # compatibility no-op
    _alert_mode()  # compatibility no-op
    reasons = _reasons_list(
        reason,
        [
            "Options premiums elevated or expensive",
            "Spread/liquidity not ideal",
            "Cleaner risk with shares",
        ],
    )
    score_raw = None
    if isinstance(signal.features, dict):
        score_raw = signal.features.get("score")
    try:
        confidence = round(float(score_raw) / 10, 1) if score_raw is not None else 7.5
    except (TypeError, ValueError):
        confidence = 7.5
    payload = {
        "ticker": signal.ticker,
        "bias": "Bullish" if signal.direction == "bull" else "Bearish",
        "market_context": _market_context(signal.setup_name),
        "trigger": _fmt_price(signal.entry_trigger),
        "invalidation": _fmt_price(signal.stop),
        "targets": [
            _fmt_price(signal.targets[0]) if signal.targets else None,
            _fmt_price(signal.targets[1]) if signal.targets and len(signal.targets) > 1 else None,
        ],
        "reasons": reasons,
        "execution_plan": "Respect the plan and scale only at targets.",
        "confidence": confidence,
    }
    return render_stock_alert(payload)


def format_im_in(trade) -> str:
    _alert_style()  # compatibility no-op
    instrument_type = "CALL" if (getattr(trade, "side", "bullish") or "").startswith("bull") else "PUT"
    payload = {
        "ticker": trade.ticker,
        "instrument_type": instrument_type if getattr(trade, "option_symbol", None) else "STOCK",
        "fill_price": _fmt_price(getattr(trade, "entry_price", None) or getattr(trade, "entry_trigger_price", None)),
        "stop_price": _fmt_price(getattr(trade, "stop_price", None)),
        "plan": "Trade live. Hard stop stays in.",
        "timestamp": getattr(trade, "opened_at", None),
    }
    return render_in_alert(payload)


def format_im_out(trade) -> str:
    _alert_style()  # compatibility no-op
    instrument_type = "CALL" if (getattr(trade, "side", "bullish") or "").startswith("bull") else "PUT"
    entry = getattr(trade, "entry_price", None) or getattr(trade, "entry_trigger_price", None)
    exit_fill = getattr(trade, "last_price", None)
    pnl_pct = None
    try:
        if entry is not None and exit_fill is not None:
            direction_mult = 1 if (getattr(trade, "side", "bullish") or "").startswith("bull") else -1
            pnl_pct = ((float(exit_fill) - float(entry)) * direction_mult / float(entry)) * 100
    except Exception:  # noqa: BLE001
        pnl_pct = None

    payload = {
        "ticker": trade.ticker,
        "instrument_type": instrument_type if getattr(trade, "option_symbol", None) else "STOCK",
        "exit_price": _fmt_price(exit_fill),
        "pnl_pct": pnl_pct,
        "pnl_abs": None,
        "reason": getattr(trade, "exit_reason", None) or "target hit",
        "timestamp": getattr(trade, "closed_at", None),
    }
    return render_out_alert(payload)


trade_idea_with_options = format_trade_idea_with_options
trade_idea_stock_only = format_trade_idea_stock_only
im_in = format_im_in
im_out = format_im_out
