"""Utilities for working with OHLCV bars."""

from __future__ import annotations

from typing import Any, Dict


def _get_nested(source: Dict[str, Any], field: str) -> Any:
    """Best-effort nested lookup for Massive day.* payloads."""

    if not isinstance(source, dict):
        return None
    day = source.get("day") or {}
    if isinstance(day, dict):
        return day.get(field)
    return None


def normalize_bar(bar: dict) -> dict:
    """
    Normalize various OHLCV bar shapes into a common dictionary.

    Keys guaranteed when present in the source:
    - open, high, low, close, volume
    - vwap (optional)
    - timestamp (optional)
    """

    normalized = {
        "open": bar.get("open", bar.get("o")) or _get_nested(bar, "open"),
        "high": bar.get("high", bar.get("h")) or _get_nested(bar, "high"),
        "low": bar.get("low", bar.get("l")) or _get_nested(bar, "low"),
        "close": bar.get("close", bar.get("c")) or _get_nested(bar, "close"),
        "volume": bar.get("volume", bar.get("v")) or _get_nested(bar, "volume"),
    }

    vwap = bar.get("vwap", bar.get("vw")) or _get_nested(bar, "vwap")
    if vwap is not None:
        normalized["vwap"] = vwap

    timestamp = bar.get("timestamp", bar.get("t")) or _get_nested(bar, "timestamp")
    if timestamp is not None:
        normalized["timestamp"] = timestamp

    return normalized
