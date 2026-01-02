from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class BreakoutVolumeDetector(SetupDetector):
    name = "breakout_volume"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if len(ohlcv) < 2:
            return None
        last = ohlcv[-1]
        prev = ohlcv[-2]
        range_high = max(candle["high"] for candle in ohlcv[:-1])
        if last["close"] > range_high and last["volume"] > prev["volume"] * 1.2:
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
                features={"volume_ratio": last["volume"] / max(prev["volume"], 1)},
                regime="TREND",
            )
        return None
