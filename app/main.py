import logging
import os
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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
def health(request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    try:
        session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception:  # noqa: BLE001
        return {"status": "error", "db": "unavailable"}


def _env_bool(var_name: str, default: bool) -> bool:
    return os.getenv(var_name, str(default)).lower() == "true"


def _env_int(var_name: str, default: int) -> int:
    try:
        return int(os.getenv(var_name, str(default)))
    except ValueError:
        return default


@app.get("/preflight")
def preflight(request: Request):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_connected = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Preflight DB check failed: %s", exc)
        db_connected = False

    return {
        "status": "ok",
        "telegram_enabled": _env_bool("TELEGRAM_ENABLED", False),
        "db_connected": db_connected,
        "enable_rth_only": _env_bool("ENABLE_RTH_ONLY", True),
        "universe_size": _env_int("UNIVERSE_SIZE", 20),
        "service_time_utc": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/test/telegram")
def test_telegram(request: Request):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /test/telegram")
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
        response = {
            "status": "sent",
            "chat_id": chat_id,
            "telegram_ok": bool(result.get("ok")),
            "telegram_status_code": result.get("status_code"),
            "telegram_response": _truncate_response(result.get("response")),
        }
        logger.info("JOB END /test/telegram result=%s", response)
        return response
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
        logger.exception("JOB ERROR /test/telegram")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "detail": str(exc),
                "telegram_status_code": status_code,
                "telegram_response": _truncate_response(response_data),
            },
        )


@app.post("/universe/rebuild")
def rebuild_universe(request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /universe/rebuild")
    try:
        tickers = universe_service.build_universe(session)
        response = {"count": len(tickers)}
        logger.info("JOB END /universe/rebuild result=%s", response)
        return response
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /universe/rebuild")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )


def run_scan(timeframe: str, session):
    if not _within_rth():
        return {"message": "outside RTH window"}
    client = MassiveClient()
    signals = []
    tickers = universe_service.latest_universe(session)
    start_time = datetime.utcnow()
    processed = 0
    for ticker in tickers:
        if processed >= settings.max_tickers_per_run:
            logger.info("Stopping scan after hitting MAX_TICKERS_PER_RUN=%s", settings.max_tickers_per_run)
            break
        if (datetime.utcnow() - start_time).total_seconds() > settings.max_runtime_seconds:
            logger.info("Stopping scan after hitting runtime limit %ss", settings.max_runtime_seconds)
            break
        ohlcv = client.get_aggregates(ticker)
        # attach ticker
        for candle in ohlcv:
            candle["ticker"] = ticker
        for detector in _detectors():
            sig = detector.detect(ohlcv)
            if sig:
                scored = score_signal(sig)
                sig.features["score"] = scored.total
                logger.info("Signal candidate %s score=%s setup=%s", ticker, scored.total, sig.setup_name)
                signals.append((sig, scored.total))
                break
        processed += 1
    if not signals:
        return {"message": "no signals"}
    # pick best signal
    signal, score = sorted(signals, key=lambda x: x[1], reverse=True)[0]
    logger.info("Top signal %s score=%s setup=%s", signal.ticker, score, signal.setup_name)
    allowed, reason = allow_trade(session, signal.ticker)
    if not allowed:
        return {"blocked": reason}
    option_snapshot = client.get_options_chain_snapshot(signal.ticker)
    option_decision = select_option(signal, option_snapshot, underlying_price=signal.entry_trigger)
    logger.info(
        "Option decision for %s chosen=%s reason=%s",
        signal.ticker,
        bool(option_decision.contract),
        option_decision.reason,
    )
    if option_decision.contract:
        message = trade_idea_with_options(signal, option_decision.contract)
    else:
        message = trade_idea_stock_only(signal, option_decision.reason or "Options unavailable")
    send_message(message)
    create_trade(session, signal, option_symbol=option_decision.contract.get("symbol") if option_decision.contract else None)
    return {"signal": signal.ticker, "score": score}


@app.post("/scan/{tf}")
def scan(tf: str, request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    if tf not in {"scalp", "day", "swing"}:
        raise HTTPException(400, "invalid timeframe")
    if tf != "day":
        return run_scan(tf, session)
    logger.info("JOB START /scan/day")
    try:
        result = run_scan(tf, session)
        logger.info("JOB END /scan/day result=%s", result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /scan/day")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )


@app.post("/state/update")
def state_update(request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /state/update")
    if not _within_rth():
        return {"message": "outside RTH window"}
    client = MassiveClient()

    def price_lookup(ticker: str):
        snap = client.get_snapshot(ticker)
        return snap.get("last", 0) or 0
    try:
        updated = update_trade_states(session, price_lookup)
        messages = []
        for trade in updated:
            if trade.state == "IN_POSITION":
                messages.append(
                    send_message(
                        f"✅ I'M IN — {trade.ticker} at {trade.entry_fill:.2f} (trigger {trade.entry_trigger:.2f})"
                    )
                )
            elif trade.state == "CLOSED":
                pnl_text = ""
                if trade.entry_fill and trade.exit_fill:
                    pnl = (trade.exit_fill - trade.entry_fill) * (1 if trade.direction == "bull" else -1)
                    pnl_pct = (pnl / trade.entry_fill) * 100
                    pnl_text = f" P/L≈{pnl:.2f} ({pnl_pct:.2f}%)"
                messages.append(
                    send_message(
                        f"🏁 I'M OUT — {trade.ticker} {trade.exit_reason or ''}"
                        f" entry={trade.entry_fill or trade.entry_trigger:.2f}"
                        f" exit={trade.exit_fill or trade.t2:.2f}"
                        f" stop={trade.stop:.2f} targets=({trade.t1:.2f},{trade.t2:.2f})" + pnl_text
                    )
                )
        response = {"updated": len(updated), "messages": len(messages)}
        logger.info("JOB END /state/update result=%s", response)
        return response
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /state/update")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )


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
