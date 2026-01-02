from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class SignalCandidate:
    ticker: str
    timeframe: str
    direction: str
    setup_name: str
    entry_trigger: float
    stop: float
    targets: List[float]
    reasons: List[str]
    features: Dict[str, float]
    regime: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class SetupDetector:
    name = "base"

    def detect(self, ohlcv: List[dict]) -> Optional[SignalCandidate]:
        raise NotImplementedError
