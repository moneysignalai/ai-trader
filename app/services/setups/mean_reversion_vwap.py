from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class MeanReversionToVwapDetector(SetupDetector):
    name = "mean_reversion_vwap"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if not ohlcv:
            return None
        last = ohlcv[-1]
        if last.get("far_from_vwap"):
            entry = last["close"]
            stop = last["close"] - 0.4
            targets = [entry + 0.3, entry + 0.6]
            return SignalCandidate(
                ticker=last.get("ticker", "TST"),
                timeframe="scalp",
                direction="bull",
                setup_name=self.name,
                entry_trigger=entry,
                stop=stop,
                targets=targets,
                reasons=["Extended from VWAP", "Expecting mean reversion"],
                features={"extension": 2.0},
                regime="RANGE",
            )
        return None
