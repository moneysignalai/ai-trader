from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.db import Base


@dataclass
class Universe:
    date: str
    tickers_json: List[str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None


@dataclass
class Signal:
    ticker: str
    timeframe: str
    setup_name: str
    direction: str
    score: int
    regime: str
    entry: float
    stop: float
    t1: float
    t2: float
    reasons_json: List[str]
    features_json: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None


@dataclass
class OptionsPick:
    signal_id: int
    contract_symbol: Optional[str] = None
    exp: Optional[str] = None
    strike: Optional[float] = None
    type: Optional[str] = None
    delta: Optional[float] = None
    iv: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    oi: Optional[int] = None
    volume: Optional[int] = None
    premium: Optional[float] = None
    value_score: Optional[float] = None
    status: Optional[str] = None
    reject_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None


@dataclass
class Trade:
    ticker: str
    timeframe: str
    setup_name: str
    direction: str
    state: str
    entry_trigger: float
    stop: float
    t1: float
    t2: float
    entry_fill: Optional[float] = None
    option_symbol: Optional[str] = None
    opened_at: datetime = field(default_factory=datetime.utcnow)
    entered_at: Optional[datetime] = None
    exited_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    telegram_msg_ids_json: Optional[Dict[str, str]] = field(default_factory=dict)
    id: Optional[int] = None


@dataclass
class AlertSent:
    trade_id: int
    alert_type: str
    telegram_message_id: Optional[str] = None
    sent_at: datetime = field(default_factory=datetime.utcnow)
    payload_json: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


@dataclass
class Outcome:
    trade_id: int
    max_favorable_move_pct: Optional[float] = None
    max_adverse_move_pct: Optional[float] = None
    notes_json: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


# register in dummy metadata for cleanup
Base.metadata.tables = {
    Universe: [],
    Signal: [],
    OptionsPick: [],
    Trade: [],
    AlertSent: [],
    Outcome: [],
}
