from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class TrendPullbackDetector(SetupDetector):
    name = "trend_pullback"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if len(ohlcv) < 3:
            return None
        last = ohlcv[-1]
        prev = ohlcv[-2]
        # simple heuristic: rising highs and lows
        if prev["low"] < last["low"] and prev["high"] < last["high"]:
            entry = last["high"] + 0.1
            stop = last["low"] - 0.1
            targets = [entry + 0.5, entry + 1.0]
            return SignalCandidate(
                ticker=last.get("ticker", "TST"),
                timeframe="day",
                direction="bull",
                setup_name=self.name,
                entry_trigger=entry,
                stop=stop,
                targets=targets,
                reasons=["Pullback held", "Trend intact"],
                features={"slope": 1.0},
                regime="TREND",
            )
        return None
