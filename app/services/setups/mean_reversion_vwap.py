from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class MeanReversionToVwapDetector(SetupDetector):
    name = "mean_reversion_vwap"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if not ohlcv:
            return None
        last = ohlcv[-1]
        vwap = last.get("vwap")
        close = last.get("close")
        atr = last.get("atr14") or 0.5
        if vwap is None or close is None:
            return None
        distance = vwap - close
        far_from_vwap = distance > max(0.3, 0.5 * atr)
        if far_from_vwap:
            entry = close
            stop = close - max(0.4, 0.6 * atr)
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
                features={"extension": distance, "risk": atr},
                regime="RANGE",
            )
        return None
