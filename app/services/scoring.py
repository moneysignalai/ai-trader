from typing import Dict, List
from app.services.setups.base import SignalCandidate


class ScoreResult:
    def __init__(self, total: float, components: Dict[str, float], reasons: List[str]):
        self.total = total
        self.components = components
        self.reasons = reasons


def score_signal(signal: SignalCandidate) -> ScoreResult:
    # transparent simple weights using features where provided
    components = {
        "trend_alignment": min(signal.features.get("slope", 1.0) * 10, 25),
        "momentum": min(signal.features.get("momentum", 1.0) * 8, 20),
        "volume": min(signal.features.get("volume_ratio", 1.0) * 10, 20),
        "volatility": min(signal.features.get("volatility", 1.0) * 5, 10),
        "risk": 15,
        "regime_fit": 8 if signal.regime else 5,
    }
    total = sum(components.values())
    reasons = signal.reasons[:4]
    if total > 90:
        reasons.append("High quality look")
    return ScoreResult(total=total, components=components, reasons=reasons)
