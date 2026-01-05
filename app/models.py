from datetime import datetime, date
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Universe(Base):
    __tablename__ = "universes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    tickers_json: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    timeframe: Mapped[str] = mapped_column(String(16))
    setup_name: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(8))
    score: Mapped[int] = mapped_column(Integer)
    regime: Mapped[str] = mapped_column(String(16))
    entry: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    t1: Mapped[float] = mapped_column(Float)
    t2: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[list[str]] = mapped_column(JSON)
    features_json: Mapped[Dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class OptionsPick(Base):
    __tablename__ = "options_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(Integer, index=True)
    contract_symbol: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    strike: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    delta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iv: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ask: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    oi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    premium: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_uuid: Mapped[str] = mapped_column(Text, unique=True, nullable=True, default=lambda: str(uuid4()))
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False, default="day", server_default="day")
    ticker: Mapped[str] = mapped_column(String, index=True)
    setup: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    side: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True, default="PENDING")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_trigger_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_prices: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)
    last_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_favorable: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alert_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_alert_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    option_symbol: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_trigger: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    t1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    t2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class AlertSent(Base):
    __tablename__ = "alerts_sent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, index=True)
    alert_type: Mapped[str] = mapped_column(String(32))
    telegram_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    payload_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, index=True)
    max_favorable_move_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_adverse_move_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class GovernorCooldown(Base):
    __tablename__ = "governor_cooldowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, index=True, unique=True)
    last_alert_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    alerts_today: Mapped[int] = mapped_column(Integer, default=0)
    as_of_date: Mapped[date] = mapped_column(Date, index=True, default=date.today)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class TradeEvent(Base):
    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    instrument_type: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(16))
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at_et_text: Mapped[str] = mapped_column(Text, nullable=False)
