from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class VwapReclaimDetector(SetupDetector):
    name = "vwap_reclaim"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if not ohlcv:
            return None
        last = ohlcv[-1]
        prev = ohlcv[-2] if len(ohlcv) > 1 else None
        vwap = last.get("vwap", last.get("close"))
        close = last.get("close")
        if vwap is None or close is None:
            return None
        reclaimed = last.get("above_vwap") and (prev is None or not prev.get("above_vwap"))
        if reclaimed:
            entry = last["close"] + 0.05
            stop = last["close"] - 0.3
            targets = [entry + 0.4, entry + 0.8]
            return SignalCandidate(
                ticker=last.get("ticker", "TST"),
                timeframe="day",
                direction="bull",
                setup_name=self.name,
                entry_trigger=entry,
                stop=stop,
                targets=targets,
                reasons=["VWAP reclaimed", "Momentum confirmed"],
                features={"vwap_reclaim": 1, "momentum": (close - vwap)},
                regime="TREND",
            )
        return None
