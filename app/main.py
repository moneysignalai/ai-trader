import logging
import os
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text

from app.config import get_settings, is_rth_now
from app.logging_config import configure_logging
from app.db import Base, engine, get_session
from app import models
from app.services import universe as universe_service
from app.services.massive_client import MassiveClient
from app.services.setups.trend_pullback import TrendPullbackDetector
from app.services.setups.breakout_volume import BreakoutVolumeDetector
from app.services.setups.vwap_reclaim import VwapReclaimDetector
from app.services.setups.mean_reversion_vwap import MeanReversionToVwapDetector
from app.services.setups.bb_squeeze import BollingerSqueezeDetector
from app.services.setups.reversal_divergence import ReversalDivergenceDetector
from app.services.scoring import score_signal
from app.services.governor import allow_trade
from app.services.trade_state import create_trade, update_trade_states
from app.services.options_selector import select_option
from app.services.templates import trade_idea_with_options, trade_idea_stock_only
from app.services.telegram import send_message, send_message_with_http_response

configure_logging()
settings = get_settings()
logger = logging.getLogger(__name__)

logger.info(
    "Telegram enabled: %s (TELEGRAM_ENABLED=%s)",
    settings.telegram_enabled,
    os.getenv("TELEGRAM_ENABLED"),
)
app = FastAPI(title="AI Trader Alert Engine")
Base.metadata.create_all(bind=engine)


def _within_rth() -> bool:
    return not settings.enable_rth_only or is_rth_now(settings)


def _detectors():
    return [
        TrendPullbackDetector(),
        BreakoutVolumeDetector(),
        VwapReclaimDetector(),
        MeanReversionToVwapDetector(),
        BollingerSqueezeDetector(),
        ReversalDivergenceDetector(),
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/test/telegram")
def test_telegram():
    timestamp = datetime.now().isoformat()
    message = (
        "🚨 TEST ALERT\n"
        "This is a system test.\n"
        "If you see this, Telegram integration is working.\n"
        f"Timestamp: {timestamp}"
    )

    def _truncate_response(resp: object) -> object:
        if isinstance(resp, str) and len(resp) > 500:
            return resp[:500] + "..."
        return resp

    chat_id = settings.telegram_chat_id
    try:
        result = send_message_with_http_response(message)
    except Exception as exc:  # noqa: BLE001
        status_code = None
        response_data = None
        if hasattr(exc, "response") and getattr(exc, "response") is not None:
            response_obj = getattr(exc, "response")
            status_code = getattr(response_obj, "status_code", None)
            try:
                response_data = response_obj.json()
            except Exception:  # noqa: BLE001
                response_data = getattr(response_obj, "text", None)
        return {
            "status": "error",
            "chat_id": chat_id,
            "detail": str(exc),
            "telegram_status_code": status_code,
            "telegram_response": _truncate_response(response_data),
        }

    return {
        "status": "sent",
        "chat_id": chat_id,
        "telegram_ok": bool(result.get("ok")),
        "telegram_status_code": result.get("status_code"),
        "telegram_response": _truncate_response(result.get("response")),
    }


@app.post("/universe/rebuild")
def rebuild_universe(session=Depends(get_session)):
    tickers = universe_service.build_universe(session)
    return {"count": len(tickers)}


def run_scan(timeframe: str, session):
    if not _within_rth():
        return {"message": "outside RTH window"}
    client = MassiveClient(base_path="app/tests/fixtures")
    signals = []
    tickers = universe_service.latest_universe(session)
    for ticker in tickers[:5]:
        ohlcv = client.get_aggregates(ticker)
        # attach ticker
        for candle in ohlcv:
            candle["ticker"] = ticker
        for detector in _detectors():
            sig = detector.detect(ohlcv)
            if sig:
                scored = score_signal(sig)
                sig.features["score"] = scored.total
                signals.append((sig, scored.total))
                break
    if not signals:
        return {"message": "no signals"}
    # pick best signal
    signal, score = sorted(signals, key=lambda x: x[1], reverse=True)[0]
    allowed, reason = allow_trade(session, signal.ticker)
    if not allowed:
        return {"blocked": reason}
    option_decision = select_option(signal, client.get_options_chain_snapshot(signal.ticker), underlying_price=signal.entry_trigger)
    if option_decision.contract:
        message = trade_idea_with_options(signal, option_decision.contract)
    else:
        message = trade_idea_stock_only(signal, option_decision.reason or "Options unavailable")
    send_message(message)
    create_trade(session, signal, option_symbol=option_decision.contract.get("symbol") if option_decision.contract else None)
    return {"signal": signal.ticker, "score": score}


@app.post("/scan/{tf}")
def scan(tf: str, session=Depends(get_session)):
    if tf not in {"scalp", "day", "swing"}:
        raise HTTPException(400, "invalid timeframe")
    return run_scan(tf, session)


@app.post("/state/update")
def state_update(session=Depends(get_session)):
    if not _within_rth():
        return {"message": "outside RTH window"}
    client = MassiveClient(base_path="app/tests/fixtures")
    def price_lookup(ticker: str):
        snap = client.get_snapshot(ticker)
        return snap.get("last", 0) or 0
    updated = update_trade_states(session, price_lookup)
    messages = []
    for trade in updated:
        if trade.state == "IN_POSITION":
            messages.append(send_message(f"✅ I'M IN — {trade.ticker}"))
        elif trade.state == "CLOSED":
            messages.append(send_message(f"🏁 I'M OUT — {trade.ticker} {trade.exit_reason}"))
    return {"updated": len(updated)}


@app.get("/debug/trades")
def debug_trades(session=Depends(get_session)):
    if settings.env != "dev":
        raise HTTPException(403, "forbidden")
    trades = session.execute(text("SELECT ticker,state FROM trades")).fetchall()
    return {"trades": [dict(row) for row in trades]}


@app.get("/debug/signals")
def debug_signals(session=Depends(get_session)):
    if settings.env != "dev":
        raise HTTPException(403, "forbidden")
    signals = session.execute(text("SELECT ticker,score FROM signals")).fetchall()
    return {"signals": [dict(row) for row in signals]}
