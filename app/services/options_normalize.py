from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _midpoint(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


def _spread_pct(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    mid = _midpoint(bid, ask)
    if bid is None or ask is None or mid in (None, 0):
        return None
    return ((ask - bid) / mid) * 100


def _expiration_iso(expiration: Any) -> Optional[str]:
    if not expiration:
        return None
    exp_str = str(expiration)
    exp_core = exp_str.split("T", 1)[0]
    try:
        return datetime.fromisoformat(exp_core).date().isoformat()
    except ValueError:
        return exp_core if exp_core else None


def _option_type(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).lower()
    if text.startswith("c"):
        return "call"
    if text.startswith("p"):
        return "put"
    return text or None


def normalize_options_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = snapshot.get("results") if isinstance(snapshot, dict) else []
    if not isinstance(results, list):
        return []

    normalized: List[Dict[str, Any]] = []

    for raw in results:
        raw = raw or {}
        details = raw.get("details") or raw.get("option") or {}
        last_quote = raw.get("last_quote") or raw.get("lastQuote") or {}
        last_trade = raw.get("last_trade") or raw.get("lastTrade") or {}
        greeks = raw.get("greeks") or {}
        day = raw.get("day") or {}
        iv_info = raw.get("implied_volatility") or {}

        bid = _safe_float(raw.get("bid") if raw.get("bid") is not None else last_quote.get("bid"))
        ask = _safe_float(raw.get("ask") if raw.get("ask") is not None else last_quote.get("ask"))
        last_price = _safe_float(raw.get("last") if raw.get("last") is not None else last_trade.get("price"))

        strike = raw.get("strike")
        if strike is None:
            strike = details.get("strike_price")

        expiration = raw.get("expiration") or details.get("expiration_date")

        contract = {
            "symbol": raw.get("symbol") or details.get("ticker"),
            "option_type": _option_type(raw.get("option_type") or raw.get("type") or details.get("contract_type")),
            "strike": strike,
            "expiration": _expiration_iso(expiration),
            "bid": bid,
            "ask": ask,
            "last": last_price,
            "mid": _midpoint(bid, ask),
            "spread_pct": _spread_pct(bid, ask),
            "delta": _safe_float(raw.get("delta") if raw.get("delta") is not None else greeks.get("delta")),
            "iv": _safe_float(raw.get("iv") if raw.get("iv") is not None else iv_info.get("iv")),
            "volume": raw.get("volume") if raw.get("volume") is not None else day.get("volume"),
            "open_interest": raw.get("open_interest")
            if raw.get("open_interest") is not None
            else day.get("open_interest"),
        }

        normalized.append(contract)

    return normalized
