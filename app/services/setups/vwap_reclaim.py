from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class VwapReclaimDetector(SetupDetector):
    name = "vwap_reclaim"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if not ohlcv:
            return None
        last = ohlcv[-1]
        if last.get("above_vwap"):
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
                features={"vwap_reclaim": 1},
                regime="TREND",
            )
        return None
