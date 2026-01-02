from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional
from app.config import get_settings
from app.services.setups.base import SignalCandidate


class OptionDecision:
    def __init__(self, contract: Optional[Dict], value_score: float, reason: Optional[str] = None):
        self.contract = contract
        self.value_score = value_score
        self.reason = reason


def _spread_ok(bid: float, ask: float, settings) -> bool:
    if bid is None or ask is None:
        return False
    spread = ask - bid
    mid = (ask + bid) / 2 if (ask and bid) else ask or bid
    if mid is None or mid == 0:
        return False
    return spread <= settings.max_bid_ask_spread_abs and (spread / mid) <= settings.max_bid_ask_spread_pct


def select_option(signal: SignalCandidate, chain_snapshot: Dict, underlying_price: float) -> OptionDecision:
    settings = get_settings()
    desired_type = "call" if signal.direction == "bull" else "put"
    timeframe = signal.timeframe
    now = datetime.utcnow().date()

    if not settings.options_enabled or settings.options_only_if_score_at_least > 100:
        return OptionDecision(None, 0, reason="Options disabled")

    legs = chain_snapshot.get("results", [])
    filtered = []
    for leg in legs:
        leg_type = leg.get("option_type") or leg.get("type")
        if leg_type.lower() != desired_type:
            continue
        exp_str = leg.get("expiration")
        if not exp_str:
            continue
        exp_date = datetime.fromisoformat(exp_str).date()
        dte = (exp_date - now).days
        delta = abs(leg.get("delta", 0))
        if timeframe == "scalp" and not (settings.dte_scalp_min <= dte <= settings.dte_scalp_max):
            continue
        if timeframe == "day" and not (settings.dte_day_min <= dte <= settings.dte_day_max):
            continue
        if timeframe == "swing" and not (settings.dte_swing_min <= dte <= settings.dte_swing_max):
            continue
        delta_min = getattr(settings, f"delta_{timeframe}_min", 0.3)
        delta_max = getattr(settings, f"delta_{timeframe}_max", 0.6)
        if not (delta_min <= delta <= delta_max):
            continue
        bid = leg.get("bid") or 0
        ask = leg.get("ask") or 0
        if not _spread_ok(bid, ask, settings):
            continue
        if leg.get("open_interest", 0) < settings.min_oi or leg.get("volume", 0) < settings.min_option_volume:
            continue
        premium = (bid + ask) / 2 if (bid and ask) else leg.get("last", 0)
        if timeframe == "scalp" and premium > settings.max_premium_scalp:
            continue
        if timeframe == "day" and premium > settings.max_premium_day:
            continue
        if timeframe == "swing" and premium > settings.max_premium_swing:
            continue
        filtered.append({"contract": leg, "premium": premium, "delta": delta, "dte": dte})

    if not filtered:
        return OptionDecision(None, 0, reason="Options too expensive or illiquid")

    best = sorted(filtered, key=lambda x: (abs((getattr(settings, f"delta_{signal.timeframe}_min", 0.3) + getattr(settings, f"delta_{signal.timeframe}_max", 0.6))/2 - x["delta"]), x["premium"]))[0]
    value_score = 100 - best["premium"] * 10
    return OptionDecision(contract=best["contract"], value_score=value_score)
