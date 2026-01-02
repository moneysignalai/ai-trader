from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class ReversalDivergenceDetector(SetupDetector):
    name = "reversal_divergence"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if not ohlcv:
            return None
        last = ohlcv[-1]
        if last.get("divergence"):
            entry = last["close"]
            stop = entry - 0.6
            targets = [entry + 0.6, entry + 1.0]
            return SignalCandidate(
                ticker=last.get("ticker", "TST"),
                timeframe="swing",
                direction="bull",
                setup_name=self.name,
                entry_trigger=entry,
                stop=stop,
                targets=targets,
                reasons=["Momentum divergence", "Structure break"],
                features={"divergence": 1},
                regime="RANGE",
            )
        return None
