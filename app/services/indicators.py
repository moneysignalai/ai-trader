from __future__ import annotations
from typing import List
import math


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    ema_values = [values[0]]
    for price in values[1:]:
        ema_values.append(price * k + ema_values[-1] * (1 - k))
    return ema_values


def sma(values: List[float], period: int) -> List[float]:
    out = []
    for i in range(len(values)):
        window = values[max(0, i - period + 1) : i + 1]
        out.append(sum(window) / len(window))
    return out


def rsi(values: List[float], period: int = 14) -> List[float]:
    if len(values) < 2:
        return []
    gains = []
    losses = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains[: period]) / period if gains[:period] else 0
    avg_loss = sum(losses[: period]) / period if losses[:period] else 0
    rsis = [50] * len(values)
    for i in range(period, len(values)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            rs = math.inf
        else:
            rs = avg_gain / avg_loss
        rsis[i] = 100 - (100 / (1 + rs))
    return rsis


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    if not values:
        return [], [], []
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    trs = []
    for i in range(len(highs)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    out = []
    for i in range(len(trs)):
        window = trs[max(0, i - period + 1) : i + 1]
        out.append(sum(window) / len(window))
    return out


def vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> List[float]:
    cumulative_vp = 0
    cumulative_vol = 0
    vwaps = []
    for h, l, c, v in zip(highs, lows, closes, volumes):
        typical_price = (h + l + c) / 3
        cumulative_vp += typical_price * v
        cumulative_vol += v
        vwaps.append(cumulative_vp / cumulative_vol if cumulative_vol else typical_price)
    return vwaps


def bollinger_bands(values: List[float], period: int = 20, std_mult: float = 2.0):
    sma_values = sma(values, period)
    upper, lower = [], []
    for i in range(len(values)):
        window = values[max(0, i - period + 1) : i + 1]
        mean = sma_values[i]
        variance = sum((x - mean) ** 2 for x in window) / len(window) if window else 0
        std = math.sqrt(variance)
        upper.append(mean + std_mult * std)
        lower.append(mean - std_mult * std)
    bandwidth = [((u - l) / m) if m else 0 for u, l, m in zip(upper, lower, sma_values)]
    return upper, sma_values, lower, bandwidth


def adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14):
    plus_dm = [0]
    minus_dm = [0]
    for i in range(1, len(highs)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
    tr = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr_values = sma(tr, period)
    plus_di = [0]
    minus_di = [0]
    adx_vals = [0]
    for i in range(1, len(highs)):
        if atr_values[i] == 0:
            plus_di.append(0)
            minus_di.append(0)
            adx_vals.append(0)
            continue
        plus_di.append(100 * (plus_dm[i] / atr_values[i]))
        minus_di.append(100 * (minus_dm[i] / atr_values[i]))
        dx = abs(plus_di[i] - minus_di[i]) / max(plus_di[i] + minus_di[i], 1) * 100
        adx_vals.append(dx if i == 1 else (adx_vals[-1] * (period - 1) + dx) / period)
    return adx_vals, plus_di, minus_di

