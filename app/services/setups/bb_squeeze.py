from typing import List, Optional
from app.services.setups.base import SignalCandidate, SetupDetector


class BollingerSqueezeDetector(SetupDetector):
    name = "bb_squeeze"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        if len(ohlcv) < 2:
            return None
        last = ohlcv[-1]
        prev = ohlcv[-2]
        width_now = last.get("bb_width")
        width_prev = prev.get("bb_width") if isinstance(prev, dict) else None
        bb_upper = last.get("bb_upper")
        close = last.get("close")

        squeezing = width_prev is not None and width_prev < 0.05
        broke_out = (
            width_now is not None
            and width_prev is not None
            and width_now > width_prev * 1.2
            and close is not None
            and bb_upper is not None
            and close > bb_upper
        )

        if squeezing and broke_out:
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
                features={"bandwidth": width_now or 0, "volatility": width_now or 0},
                regime="TREND",
            )
        return None
