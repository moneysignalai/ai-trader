from app.services.setups.trend_pullback import TrendPullbackDetector
from app.services.setups.breakout_volume import BreakoutVolumeDetector
from app.services.setups.vwap_reclaim import VwapReclaimDetector


def test_trend_pullback_detects():
    detector = TrendPullbackDetector()
    candles = [
        {"high": 10, "low": 9, "close": 9.5},
        {"high": 11, "low": 9.5, "close": 10},
        {"high": 12, "low": 10.5, "close": 11, "ticker": "TST"},
    ]
    signal = detector.detect(candles)
    assert signal
    assert signal.direction == "bull"


def test_breakout_volume_detects():
    detector = BreakoutVolumeDetector()
    candles = [
        {"high": 10, "low": 9, "close": 9.5, "volume": 100},
        {"high": 11, "low": 9.5, "close": 12, "volume": 150, "ticker": "TST"},
    ]
    signal = detector.detect(candles)
    assert signal
    assert signal.setup_name == "breakout_volume"


def test_vwap_reclaim():
    detector = VwapReclaimDetector()
    candles = [
        {"high": 10, "low": 9, "close": 9.5},
        {"high": 11, "low": 9.5, "close": 10, "above_vwap": True, "ticker": "TST"},
    ]
    signal = detector.detect(candles)
    assert signal
    assert signal.reasons[0] == "VWAP reclaimed"
