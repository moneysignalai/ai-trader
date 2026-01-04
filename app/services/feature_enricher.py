from __future__ import annotations

from typing import List

from app.services.indicators import atr, bollinger_bands, ema, rsi, sma


def _safe_get(series: List[float], idx: int) -> float | None:
    if 0 <= idx < len(series):
        return series[idx]
    return None


def enrich_bars(bars: list[dict]) -> list[dict]:
    if not bars:
        return bars

    highs = [float(bar.get("high", 0) or 0) for bar in bars]
    lows = [float(bar.get("low", 0) or 0) for bar in bars]
    closes = [float(bar.get("close", 0) or 0) for bar in bars]
    volumes = [float(bar.get("volume", 0) or 0) for bar in bars]

    # VWAP: prefer provided per-bar vwap when present; otherwise typical price
    vwaps: list[float] = []
    cumulative_vp = 0.0
    cumulative_vol = 0.0
    for high, low, close, volume, bar in zip(highs, lows, closes, volumes, bars):
        typical_price = (high + low + close) / 3 if volume else close
        price_component = float(bar.get("vwap", typical_price) or typical_price)
        cumulative_vp += price_component * volume
        cumulative_vol += volume
        vwaps.append(cumulative_vp / cumulative_vol if cumulative_vol else price_component)

    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    rsi14 = rsi(closes, 14)
    bb_upper, bb_mid, bb_lower, bb_width = bollinger_bands(closes, period=20)
    atr14 = atr(highs, lows, closes, period=14)
    vol_sma20 = sma(volumes, 20)

    enriched: list[dict] = []
    for idx, bar in enumerate(bars):
        enriched_bar = dict(bar)
        enriched_bar.update(
            {
                "vwap": vwaps[idx],
                "above_vwap": closes[idx] > vwaps[idx] if idx < len(vwaps) else False,
                "ema9": _safe_get(ema9, idx),
                "ema20": _safe_get(ema20, idx),
                "rsi14": _safe_get(rsi14, idx),
                "bb_upper": _safe_get(bb_upper, idx),
                "bb_mid": _safe_get(bb_mid, idx),
                "bb_lower": _safe_get(bb_lower, idx),
                "bb_width": _safe_get(bb_width, idx),
                "atr14": _safe_get(atr14, idx),
                "vol_sma20": _safe_get(vol_sma20, idx),
            }
        )
        vol_avg = enriched_bar.get("vol_sma20") or 0
        enriched_bar["vol_ratio"] = (enriched_bar.get("volume") or 0) / vol_avg if vol_avg else None
        enriched.append(enriched_bar)

    return enriched
