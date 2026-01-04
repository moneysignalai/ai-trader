from __future__ import annotations
from datetime import date, datetime
from typing import Dict, Optional

from app.config import get_settings
from app.services.setups.base import SignalCandidate
from app.utils.dates import normalize_any_date_to_mmddyyyy, parse_mmddyyyy


class OptionDecision:
    def __init__(self, contract: Optional[Dict], value_score: float, reason: Optional[str] = None):
        self.contract = contract
        self.value_score = value_score
        self.reason = reason

def _parse_expiration(contract: Dict) -> Optional[date]:
    raw = contract.get("expiration_iso") or contract.get("expiration")
    if not raw:
        return None
    try:
        normalized = normalize_any_date_to_mmddyyyy(str(raw))
        return parse_mmddyyyy(normalized)
    except ValueError:
        return None


def _spread_ratio(bid: Optional[float], ask: Optional[float], mid: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None
    mid_value = mid if mid is not None else (bid + ask) / 2
    if not mid_value:
        return None
    return (ask - bid) / mid_value


def select_option(signal: SignalCandidate, chain_snapshot: Dict, underlying_price: float) -> OptionDecision:
    settings = get_settings()
    desired_type = "call" if signal.direction == "bull" else "put"
    now = datetime.utcnow().date()

    if underlying_price is None:
        return OptionDecision(None, 0, reason="Missing underlying price")

    if not settings.options_enabled or settings.options_only_if_score_at_least > 100:
        return OptionDecision(None, 0, reason="Options disabled")

    legs = chain_snapshot.get("results", []) if isinstance(chain_snapshot, dict) else []
    candidates = []

    for leg in legs:
        if not isinstance(leg, dict):
            continue
        leg_type = (leg.get("option_type") or leg.get("type") or "").lower()
        if leg_type != desired_type:
            continue

        strike = leg.get("strike")
        if strike is None:
            continue

        moneyness_pct = abs(float(strike) - float(underlying_price)) / float(underlying_price)
        if moneyness_pct > settings.opt_max_moneyness_pct:
            continue

        exp_date = _parse_expiration(leg)
        if not exp_date:
            continue
        dte = (exp_date - now).days
        if dte < settings.opt_min_dte or dte > settings.opt_max_dte:
            continue

        bid = leg.get("bid")
        ask = leg.get("ask")
        if bid is None or ask is None:
            continue
        mid = leg.get("mid") if leg.get("mid") is not None else (bid + ask) / 2
        spread = leg.get("spread_pct")
        if spread is None:
            spread = _spread_ratio(bid, ask, mid)
        if spread is None or spread > settings.opt_max_spread_pct:
            continue

        volume = leg.get("volume") or 0
        open_interest = leg.get("open_interest") or 0
        if volume < settings.opt_min_volume and open_interest < settings.opt_min_oi:
            continue

        delta = leg.get("delta")
        if delta is not None:
            if desired_type == "call" and not (settings.opt_call_delta_min <= delta <= settings.opt_call_delta_max):
                continue
            if desired_type == "put" and not (settings.opt_put_delta_min <= delta <= settings.opt_put_delta_max):
                continue

        target_delta = (
            (settings.opt_call_delta_min + settings.opt_call_delta_max) / 2
            if desired_type == "call"
            else (settings.opt_put_delta_min + settings.opt_put_delta_max) / 2
        )
        primary_score = abs(delta - target_delta) if delta is not None else moneyness_pct
        liquidity_score = max(volume, open_interest)

        candidates.append(
            {
                "contract": leg,
                "primary_score": primary_score,
                "liquidity_score": liquidity_score,
                "spread": spread,
                "moneyness_pct": moneyness_pct,
                "delta": delta,
            }
        )

    if not candidates:
        return OptionDecision(None, 0, reason="Options too expensive or illiquid")

    best = sorted(
        candidates,
        key=lambda c: (
            c["primary_score"],
            -c["liquidity_score"],
            c["spread"] if c["spread"] is not None else 1,
            c["moneyness_pct"],
        ),
    )[0]

    value_score = max(0.0, 100 - (best["spread"] or 0) * 100)
    return OptionDecision(contract=best["contract"], value_score=value_score)
