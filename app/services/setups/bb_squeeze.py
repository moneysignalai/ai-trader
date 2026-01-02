from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class BollingerSqueezeDetector(SetupDetector):
    name = "bb_squeeze"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if len(ohlcv) < 2:
            return None
        last = ohlcv[-1]
        if last.get("squeeze_break"):
            entry = last["close"]
            stop = entry - 0.5
            targets = [entry + 0.5, entry + 1.0]
            return SignalCandidate(
                ticker=last.get("ticker", "TST"),
                timeframe="swing",
                direction="bull",
                setup_name=self.name,
                entry_trigger=entry,
                stop=stop,
                targets=targets,
                reasons=["Squeeze released", "Volume expanding"],
                features={"bandwidth": last.get("bandwidth", 0)},
                regime="TREND",
            )
        return None
