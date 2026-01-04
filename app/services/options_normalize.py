from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.dates import normalize_any_date_to_mmddyyyy


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def _format_expiration(expiration: Any) -> Optional[str]:
    if not expiration:
        return None

    raw = str(expiration).split("T", 1)[0]
    try:
        return normalize_any_date_to_mmddyyyy(raw)
    except ValueError:
        return None


def _compute_mid(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


def _compute_spread_pct(bid: Optional[float], ask: Optional[float], mid: Optional[float]) -> Optional[float]:
    if bid is None or ask is None or mid in (None, 0):
        return None
    return (ask - bid) / mid


def normalize_massive_option_result(item: Dict[str, Any]) -> Dict[str, Any]:
    details = item.get("details") or {}
    last_quote = item.get("last_quote") or {}
    last_trade = item.get("last_trade") or {}
    day = item.get("day") or {}
    underlying = item.get("underlying_asset") or {}
    greeks = item.get("greeks") or {}

    expiration_formatted = _format_expiration(details.get("expiration_date"))

    bid = _safe_float(last_quote.get("bid"))
    ask = _safe_float(last_quote.get("ask"))
    mid = _safe_float(last_quote.get("midpoint")) or _compute_mid(bid, ask)
    last = _safe_float(last_trade.get("price"))
    spread_pct = _compute_spread_pct(bid, ask, mid)

    return {
        "symbol": details.get("ticker"),
        "option_type": details.get("contract_type"),
        "strike": _safe_float(details.get("strike_price")),
        "expiration": expiration_formatted,
        "expiration_iso": expiration_formatted,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": last,
        "spread_pct": spread_pct,
        "volume": day.get("volume"),
        "open_interest": item.get("open_interest"),
        "underlying": underlying.get("ticker"),
        "underlying_price": _safe_float(underlying.get("price")),
        "delta": greeks.get("delta"),
        "iv": item.get("implied_volatility"),
    }


def normalize_snapshot_response(resp_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = resp_json.get("results") if isinstance(resp_json, dict) else []
    if not isinstance(results, list):
        return []
    return [normalize_massive_option_result(item or {}) for item in results]

