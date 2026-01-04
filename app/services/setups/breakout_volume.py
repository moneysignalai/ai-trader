from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class BreakoutVolumeDetector(SetupDetector):
    name = "breakout_volume"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if len(ohlcv) < 2:
            return None
        last = ohlcv[-1]
        prev = ohlcv[-2]
        highs = [candle.get("high") for candle in ohlcv[:-1] if candle.get("high") is not None]
        if not highs:
            return None
        range_high = max(highs)
        close = last.get("close")
        volume = last.get("volume")
        prev_volume = prev.get("volume")
        vol_ratio = last.get("vol_ratio")
        if (
            close is not None
            and volume is not None
            and prev_volume
            and close > range_high
            and ((vol_ratio and vol_ratio > 1.2) or volume > prev_volume * 1.2)
        ):
            entry = last["close"]
            stop = range_high - 0.2
            targets = [entry + 0.7, entry + 1.2]
            return SignalCandidate(
                ticker=last.get("ticker", "TST"),
                timeframe="scalp",
                direction="bull",
                setup_name=self.name,
                entry_trigger=entry,
                stop=stop,
                targets=targets,
                reasons=["Range break", "Volume confirmation"],
                features={"volume_ratio": vol_ratio or (volume / max(prev_volume, 1))},
                regime="TREND",
            )
        return None
