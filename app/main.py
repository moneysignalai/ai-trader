import logging
import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings, is_rth_now
from app.logging_config import configure_logging
from app.db import Base, engine, get_session
from app import models
from app.services import universe as universe_service
from app.services.bars import normalize_bar
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
from app.alerts.renderer import render_in_alert, render_out_alert
from app.services.templates import (
    format_im_in,
    format_im_out,
    format_trade_idea_stock_only,
    format_trade_idea_with_options,
)
from app.services.telegram import send_message_with_http_response, send_or_log
from app.services.trade_events import record_trade_event
from app.utils.dates import format_et_timestamp

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


@app.middleware("http")
async def log_request_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Unhandled exception during request method=%s path=%s",
            request.method,
            request.url.path,
        )
        raise


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


def _find_signal_for_ticker(ticker: str, client: MassiveClient, min_score: float):
    raw_ohlcv = client.get_aggregates(ticker)
    ohlcv = []

    for bar in raw_ohlcv:
        normalized = normalize_bar(bar)
        missing = [
            field for field in ("open", "high", "low", "close", "volume") if normalized.get(field) is None
        ]
        if missing:
            sample_keys = sorted(bar.keys()) if isinstance(bar, dict) else []
            raise ValueError(
                f"Missing OHLCV field: {missing[0]} for ticker {ticker}; bar keys={sample_keys}"
            )
        normalized["ticker"] = ticker
        ohlcv.append(normalized)

    for detector in _detectors():
        sig = detector.detect(ohlcv)
        if not sig:
            continue
        scored = score_signal(sig)
        sig.features["score"] = scored.total
        logger.info(
            "Signal candidate %s score=%s setup=%s", ticker, scored.total, sig.setup_name
        )
        if scored.total < min_score:
            logger.info("Skipping %s due to MIN_SIGNAL_SCORE=%s", ticker, min_score)
            continue
        return sig, scored
    return None


def _top_reasons(scored, limit: int = 5):
    reasons = [reason for reason in (getattr(scored, "reasons", []) or []) if reason]
    components = getattr(scored, "components", {}) or {}
    feature_notes = [f"{name}: {value:.1f}" for name, value in sorted(components.items(), key=lambda item: item[1], reverse=True)]
    combined = reasons + feature_notes
    return combined[:limit]


def _instrument_type_from_trade(trade) -> str:
    if getattr(trade, "option_symbol", None):
        return "CALL" if getattr(trade, "direction", "bull") == "bull" else "PUT"
    return "STOCK"


class TradeInRequest(BaseModel):
    ticker: str
    instrument_type: str
    fill_price: float
    stop_price: float
    plan: str | None = None
    contract: dict | None = None


class TradeOutRequest(BaseModel):
    ticker: str
    instrument_type: str
    exit_price: float
    pnl_pct: float | None = None
    pnl_abs: float | None = None
    reason: str | None = None


@app.get("/")
def root(request: Request):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )

    return {
        "ok": True,
        "service": "ai-trader",
        "health": "/health",
        "docs": "/docs",
    }


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
        "service_time_et": format_et_timestamp(),
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
    message = (
        "🚨 TEST ALERT\n"
        "This is a system test.\n"
        "If you see this, Telegram integration is working.\n"
        f"Timestamp: {format_et_timestamp()}"
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
        error_payload = {
            "status": "error",
            "chat_id": chat_id,
            "telegram_ok": False,
            "telegram_status_code": status_code,
            "telegram_response": _truncate_response(response_data),
        }
        logger.exception("JOB ERROR /test/telegram")
        return JSONResponse(status_code=500, content=error_payload)

    response = {
        "chat_id": chat_id,
        "telegram_ok": bool(result.get("ok")),
        "telegram_status_code": result.get("status_code"),
        "telegram_response": _truncate_response(result.get("response")),
    }

    if result.get("response") in {"alerts-disabled", "telegram-disabled"}:
        response["status"] = "disabled"
        logger.info("JOB END /test/telegram result=%s", response)
        return response

    if result.get("ok"):
        response["status"] = "sent"
        logger.info("JOB END /test/telegram result=%s", response)
        return response

    response["status"] = "error"
    logger.error("JOB ERROR /test/telegram result=%s", response)
    return JSONResponse(status_code=500, content=response)


@app.post("/trade/in")
def trade_in(payload: TradeInRequest, request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    if not _within_rth():
        return {"status": "blocked", "reason": "outside RTH"}

    instrument_type = payload.instrument_type.upper()
    alert = render_in_alert(
        {
            "ticker": payload.ticker,
            "instrument_type": instrument_type,
            "fill_price": payload.fill_price,
            "stop_price": payload.stop_price,
            "plan": payload.plan,
        }
    )
    send_or_log(
        alert,
        context={"endpoint": "/trade/in", "ticker": payload.ticker},
    )
    record_trade_event(
        session,
        ticker=payload.ticker,
        instrument_type=instrument_type,
        side="in",
        payload={"message": alert, "contract": payload.contract},
    )
    return {"status": "sent", "ticker": payload.ticker}


@app.post("/trade/out")
def trade_out(payload: TradeOutRequest, request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    if not _within_rth():
        return {"status": "blocked", "reason": "outside RTH"}

    instrument_type = payload.instrument_type.upper()
    alert = render_out_alert(
        {
            "ticker": payload.ticker,
            "instrument_type": instrument_type,
            "exit_price": payload.exit_price,
            "pnl_pct": payload.pnl_pct,
            "pnl_abs": payload.pnl_abs,
            "reason": payload.reason,
        }
    )
    send_or_log(
        alert,
        context={"endpoint": "/trade/out", "ticker": payload.ticker},
    )
    record_trade_event(
        session,
        ticker=payload.ticker,
        instrument_type=instrument_type,
        side="out",
        payload={"message": alert, "reason": payload.reason},
    )
    return {"status": "sent", "ticker": payload.ticker}


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


def run_scan(timeframe: str, session, request_id: str | None = None):
    if not _within_rth():
        return {"message": "outside RTH"}
    client = MassiveClient()
    signals = []
    tickers = universe_service.latest_universe(session)
    start_time = time.monotonic()
    processed = 0
    for ticker in tickers:
        if processed >= settings.max_tickers_per_run:
            logger.info("Stopping scan after hitting MAX_TICKERS_PER_RUN=%s", settings.max_tickers_per_run)
            break
        if time.monotonic() - start_time > settings.max_runtime_seconds:
            logger.info("Stopping scan after hitting runtime limit %ss", settings.max_runtime_seconds)
            break
        candidate = _find_signal_for_ticker(ticker, client, settings.min_signal_score)
        if candidate:
            sig, scored = candidate
            signals.append((sig, scored.total))
        processed += 1
    if not signals:
        return {"message": "no signals"}
    # pick best signal
    signal, score = sorted(signals, key=lambda x: x[1], reverse=True)[0]
    logger.info("Top signal %s score=%s setup=%s", signal.ticker, score, signal.setup_name)
    if settings.max_alerts_per_run <= 0:
        logger.info("MAX_ALERTS_PER_RUN=%s prevents emitting alerts", settings.max_alerts_per_run)
        return {"message": "alerts capped for this run"}
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
        instrument_type = "CALL" if signal.direction == "bull" else "PUT"
        message = format_trade_idea_with_options(signal, option_decision.contract)
    else:
        instrument_type = "STOCK"
        stock_reasons = option_decision.fallback_reasons or [
            "Options premiums elevated or expensive",
            "Spread/liquidity not ideal",
            "Cleaner risk with shares",
        ]
        message = format_trade_idea_stock_only(signal, stock_reasons)
    send_or_log(
        message,
        context={
            "endpoint": f"/scan/{timeframe}",
            "ticker": signal.ticker,
            "request_id": request_id,
        },
    )
    record_trade_event(
        session,
        ticker=signal.ticker,
        instrument_type=instrument_type,
        side="idea",
        payload={
            "message": message,
            "option_selected": bool(option_decision.contract),
            "reason": option_decision.reason,
        },
    )
    create_trade(
        session,
        signal,
        option_symbol=option_decision.contract.get("symbol") if option_decision.contract else None,
    )
    return {"signal": signal.ticker, "score": score, "alerts_sent": 1}


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
        return run_scan(tf, session, request.headers.get("x-request-id"))
    logger.info("JOB START /scan/day")
    try:
        result = run_scan(tf, session, request.headers.get("x-request-id"))
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
        return {"message": "outside RTH"}
    client = MassiveClient()

    def price_lookup(ticker: str):
        snap = client.get_snapshot(ticker)
        return snap.get("last", 0) or 0
    try:
        updated = update_trade_states(session, price_lookup)
        if not settings.enable_follow_up_alerts:
            response = {
                "updated": len(updated),
                "messages": 0,
                "follow_up_alerts_enabled": False,
            }
            logger.info("JOB END /state/update result=%s", response)
            return response

        messages = []
        for trade in updated:
            instrument_type = _instrument_type_from_trade(trade)
            if trade.state == "IN_POSITION":
                alert = format_im_in(trade)
                messages.append(
                    send_or_log(
                        alert,
                        context={
                            "endpoint": "/state/update",
                            "ticker": trade.ticker,
                            "request_id": request.headers.get("x-request-id"),
                        },
                    )
                )
                record_trade_event(
                    session,
                    ticker=trade.ticker,
                    instrument_type=instrument_type,
                    side="in",
                    payload={"message": alert},
                )
            elif trade.state == "CLOSED":
                alert = format_im_out(trade)
                messages.append(
                    send_or_log(
                        alert,
                        context={
                            "endpoint": "/state/update",
                            "ticker": trade.ticker,
                            "request_id": request.headers.get("x-request-id"),
                        },
                    )
                )
                record_trade_event(
                    session,
                    ticker=trade.ticker,
                    instrument_type=instrument_type,
                    side="out",
                    payload={"message": alert, "reason": trade.exit_reason},
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


@app.post("/debug/force-alert")
def debug_force_alert(
    request: Request,
    ticker: str,
    min_score_override: float | None = None,
    dry_run: bool = False,
    session=Depends(get_session),
):
    if os.getenv("DEBUG_ENDPOINTS_ENABLED", "false").lower() != "true":
        raise HTTPException(403, "forbidden")

    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /debug/force-alert ticker=%s", ticker)

    if not _within_rth():
        return {"message": "outside RTH"}

    used_threshold = float(min_score_override) if min_score_override is not None else settings.min_signal_score
    client = MassiveClient()

    try:
        candidate = _find_signal_for_ticker(ticker, client, used_threshold)
    except ValueError as exc:
        logger.exception("JOB ERROR /debug/force-alert")
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /debug/force-alert")
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})

    if not candidate:
        response = {
            "status": "no-signal",
            "detail": "No setup qualified at the requested threshold.",
            "used_threshold": used_threshold,
        }
        logger.info("JOB END /debug/force-alert result=%s", response)
        return JSONResponse(status_code=404, content=response)

    signal, scored = candidate
    qualifies_normally = scored.total >= settings.min_signal_score
    reasons = _top_reasons(scored)

    option_snapshot = client.get_options_chain_snapshot(signal.ticker)
    option_decision = select_option(signal, option_snapshot, underlying_price=signal.entry_trigger)
    logger.info(
        "Option decision for %s chosen=%s reason=%s",
        signal.ticker,
        bool(option_decision.contract),
        option_decision.reason,
    )
    if option_decision.contract:
        instrument_type = "CALL" if signal.direction == "bull" else "PUT"
        message = format_trade_idea_with_options(signal, option_decision.contract)
    else:
        instrument_type = "STOCK"
        stock_reasons = option_decision.fallback_reasons or [
            "Options premiums elevated or expensive",
            "Spread/liquidity not ideal",
            "Cleaner risk with shares",
        ]
        message = format_trade_idea_stock_only(signal, stock_reasons)

    response_payload = {
        "ticker": signal.ticker,
        "score": scored.total,
        "used_threshold": used_threshold,
        "qualified_normally": qualifies_normally,
        "reasons": reasons,
        "components": scored.components,
    }

    if dry_run:
        response_payload.update(
            {
                "status": "dry-run",
                "alert_message": message,
                "option_selected": bool(option_decision.contract),
                "option_reason": option_decision.reason,
                "signal": {
                    "setup": signal.setup_name,
                    "direction": signal.direction,
                    "entry": signal.entry_trigger,
                    "stop": signal.stop,
                    "targets": signal.targets,
                    "reasons": signal.reasons,
                    "features": signal.features,
                },
            }
        )
        logger.info("JOB END /debug/force-alert result=%s", response_payload)
        return response_payload

    allowed, reason = allow_trade(session, signal.ticker)
    if not allowed:
        response_payload.update({"status": "blocked", "detail": reason})
        logger.info("JOB END /debug/force-alert result=%s", response_payload)
        return JSONResponse(status_code=429, content=response_payload)

    send_result = send_or_log(
        message,
        context={
            "endpoint": "/debug/force-alert",
            "ticker": signal.ticker,
            "request_id": request.headers.get("x-request-id"),
        },
    )
    record_trade_event(
        session,
        ticker=signal.ticker,
        instrument_type=instrument_type,
        side="idea",
        payload={"message": message, "option_selected": bool(option_decision.contract)},
    )
    create_trade(
        session,
        signal,
        option_symbol=option_decision.contract.get("symbol") if option_decision.contract else None,
    )

    response_payload.update(
        {
            "status": "sent" if send_result.get("ok") else "error",
            "telegram_status_code": send_result.get("status_code"),
        }
    )
    logger.info("JOB END /debug/force-alert result=%s", response_payload)
    return response_payload
