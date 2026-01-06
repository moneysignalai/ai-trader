import logging
import os
import time
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings, is_rth_now
from app.logging_config import configure_logging
from app.db import SessionLocal, engine, get_session, table_exists
from app import models
from app.services import universe as universe_service
from app.services.bars import normalize_bar
from app.services.massive_client import MassiveClient
from app.services.feature_enricher import enrich_bars
from app.services.db_migrate import (
    describe_trades_schema,
    ensure_trades_schema,
    get_last_migration_result,
)
from app.services.setups.trend_pullback import TrendPullbackDetector
from app.services.setups.breakout_volume import BreakoutVolumeDetector
from app.services.setups.vwap_reclaim import VwapReclaimDetector
from app.services.setups.mean_reversion_vwap import MeanReversionToVwapDetector
from app.services.setups.bb_squeeze import BollingerSqueezeDetector
from app.services.setups.reversal_divergence import ReversalDivergenceDetector
from app.services.scoring import score_signal
from app.services.governor import allow_trade
from app.services.trade_state import create_trade, update_trade_states
from app.services.options_selector import OptionDecision, select_option
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
logger.info("DEBUG_ENDPOINTS_ENABLED=%s", settings.debug_endpoints_enabled)
logger.info(
    "Entry mode: %s (ENTRY_MODE=%s)", settings.entry_mode, os.getenv("ENTRY_MODE")
)
app = FastAPI(title="AI Trader Alert Engine")


@app.on_event("startup")
def apply_startup_migrations():
    if not settings.db_auto_migrate:
        logger.info("DB_AUTO_MIGRATE=false; skipping trades schema migration")
        _schema_health_check()
        return
    if not settings.database_url:
        logger.info("No DATABASE_URL configured; skipping trades schema migration")
        _schema_health_check()
        return
    try:
        result = ensure_trades_schema(engine)
        logger.info("Trades schema migration summary: %s", result)
    except Exception:  # noqa: BLE001
        logger.exception("Trades schema migration failed but server will continue")
    _schema_health_check()


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


def _extract_snapshot_price(snap: dict | None) -> float | None:
    if not isinstance(snap, dict):
        return None

    price = snap.get("last") or snap.get("last_price") or snap.get("price")
    if price is None:
        last_trade = snap.get("last_trade") if isinstance(snap.get("last_trade"), dict) else {}
        last_quote = snap.get("last_quote") if isinstance(snap.get("last_quote"), dict) else {}
        session = snap.get("session") if isinstance(snap.get("session"), dict) else {}
        price = (
            last_trade.get("price")
            or last_trade.get("p")
            or last_quote.get("price")
            or last_quote.get("p")
            or session.get("last")
            or session.get("close")
            or session.get("c")
        )

    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):  # noqa: PERF203
        return None


def get_maintenance_price(ticker: str, client: MassiveClient) -> float:
    snap = client.unified_snapshot_single_ticker(ticker, type="stocks")
    price = _extract_snapshot_price(snap)
    if price is not None:
        logger.info(
            "Price lookup: ticker=%s kind=maintenance source=unified_snapshot price=%s",
            ticker,
            price,
        )
        return price

    legacy_snap = client.get_snapshot(ticker) or {}
    legacy_price = _extract_snapshot_price(legacy_snap)
    if legacy_price is not None:
        logger.info(
            "Price lookup: ticker=%s kind=maintenance source=snapshot price=%s",
            ticker,
            legacy_price,
        )
        return legacy_price

    px = client.latest_price_from_aggregates(ticker)
    if px is not None:
        price = float(px)
        logger.info(
            "Price lookup: ticker=%s kind=maintenance source=aggregates_fallback price=%s",
            ticker,
            price,
        )
        return price

    logger.warning("Price lookup: ticker=%s kind=maintenance source=missing price=0", ticker)
    return 0.0


def get_execution_price(ticker: str, client: MassiveClient) -> float | None:
    snap = client.unified_snapshot_single_ticker(ticker, type="stocks")
    price = _extract_snapshot_price(snap)
    if price is not None:
        logger.info(
            "Price lookup: ticker=%s kind=execution source=unified_snapshot price=%s",
            ticker,
            price,
        )
        return price

    legacy_snap = client.get_snapshot(ticker) or {}
    legacy_price = _extract_snapshot_price(legacy_snap)
    if legacy_price is not None:
        logger.info(
            "Price lookup: ticker=%s kind=execution source=snapshot price=%s",
            ticker,
            legacy_price,
        )
        return legacy_price

    aggregates_px = client.latest_price_from_aggregates(ticker)
    if aggregates_px is not None:
        logger.info(
            "Price lookup: ticker=%s kind=execution source=aggregates_fallback price=%s",
            ticker,
            aggregates_px,
        )
        return float(aggregates_px)

    logger.warning(
        "Price lookup: ticker=%s kind=execution source=missing price=None", ticker
    )
    return None


def _resolve_option_decision(signal, client: MassiveClient, option_snapshot, settings):
    market_open = is_rth_now(settings)

    if market_open:
        underlying_price = get_execution_price(signal.ticker, client)
        if underlying_price is None:
            logger.warning(
                "Option decision blocked: ticker=%s market_open=True reason=Realtime price unavailable",
                signal.ticker,
            )
            return (
                OptionDecision(
                    None,
                    0,
                    reason="Realtime price unavailable",
                    fallback_reasons=[
                        "Realtime price unavailable",
                        "Cleaner risk with shares",
                    ],
                ),
                None,
                market_open,
            )
    else:
        underlying_price = get_maintenance_price(signal.ticker, client)

    decision = select_option(signal, option_snapshot, underlying_price=underlying_price)
    return decision, underlying_price, market_open


def _ideas_mode_active() -> bool:
    return (getattr(settings, "alert_mode", "ideas") or "ideas").lower() == "ideas"


def _schema_health_check():
    """Validate critical Trade fields exist and log their defaults without touching the DB."""
    try:
        dummy = models.Trade(
            ticker="SCHEMA-CHECK",
            setup="healthcheck",
            setup_name="healthcheck",
            side="bullish",
            direction="bullish",
            state="PENDING",
            status="PENDING",
            timeframe="day",
            opened_at=datetime.utcnow(),
            entry_trigger_price=0.0,
            stop=0.0,
            stop_price=0.0,
        )
        logger.info(
            "Trades startup schema sanity: direction=%s state=%s stop=%s stop_price=%s timeframe=%s",
            dummy.direction,
            dummy.state,
            dummy.stop,
            dummy.stop_price,
            dummy.timeframe,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Trades startup schema sanity check failed")


def _detectors():
    return [
        TrendPullbackDetector(),
        BreakoutVolumeDetector(),
        VwapReclaimDetector(),
        MeanReversionToVwapDetector(),
        BollingerSqueezeDetector(),
        ReversalDivergenceDetector(),
    ]


def _load_bars_for_ticker(ticker: str, client: MassiveClient) -> list[dict]:
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

    return enrich_bars(ohlcv)


def _find_signal_for_ticker(
    ticker: str, client: MassiveClient, min_score: float, return_best: bool = False
):
    ohlcv = _load_bars_for_ticker(ticker, client)

    best_candidate = None
    best_score = float("-inf")
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
            if return_best and scored.total > best_score:
                best_candidate = (sig, scored)
                best_score = scored.total
            continue
        return sig, scored
    return best_candidate if return_best else None


def _top_reasons(scored, limit: int = 5):
    reasons = [reason for reason in (getattr(scored, "reasons", []) or []) if reason]
    components = getattr(scored, "components", {}) or {}
    feature_notes = [f"{name}: {value:.1f}" for name, value in sorted(components.items(), key=lambda item: item[1], reverse=True)]
    combined = reasons + feature_notes
    return combined[:limit]


def _instrument_type_from_trade(trade) -> str:
    if getattr(trade, "option_symbol", None):
        side = getattr(trade, "side", None) or getattr(trade, "direction", "bull")
        return "CALL" if str(side).startswith("bull") else "PUT"
    return "STOCK"


def _summarize_candidate(sig, scored, threshold: float, governor_reason: str | None = None):
    would_alert = scored.total >= threshold and not governor_reason
    top_features = []
    if getattr(scored, "components", None):
        sorted_feats = sorted(scored.components.items(), key=lambda item: item[1], reverse=True)
        top_features = [name for name, _ in sorted_feats[:5]]
    failed_gates = []
    if scored.total < threshold:
        failed_gates.append(f"Score below threshold ({scored.total:.1f} < {threshold})")
    if governor_reason:
        failed_gates.append(governor_reason)
    return {
        "setup_name": sig.setup_name,
        "direction": sig.direction,
        "score": scored.total,
        "threshold_used": threshold,
        "would_alert": would_alert,
    }, top_features, failed_gates


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
def health(request: Request):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001
        db_status = "error"

    return {"status": "ok", "db": db_status}


def _env_bool(var_name: str, default: bool) -> bool:
    return os.getenv(var_name, str(default)).lower() == "true"


def _env_int(var_name: str, default: int) -> int:
    try:
        return int(os.getenv(var_name, str(default)))
    except ValueError:
        return default


def _debug_endpoints_enabled() -> bool:
    return bool(settings.debug_endpoints_enabled)


def _db_unavailable_response() -> dict[str, str]:
    return {"status": "error", "detail": "db-unavailable"}


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
    if _ideas_mode_active():
        return {"status": "suppressed", "reason": "ideas-only mode"}

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
    if _ideas_mode_active():
        return {"status": "suppressed", "reason": "ideas-only mode"}

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
    timeframe = (timeframe or "day").strip() or "day"
    if not _within_rth():
        return {"message": "outside RTH"}
    client = MassiveClient()
    signals = []
    tickers = universe_service.latest_universe(session)
    if timeframe == "day":
        if not tickers:
            logger.error("Universe empty — rebuilding")
            tickers = universe_service.build_universe(session, client=client)
        if universe_service.contains_placeholder_tickers(tickers):
            logger.error("Universe contains placeholder tickers; rebuilding")
            tickers = universe_service.build_universe(session, client=client)
        if not tickers or universe_service.contains_placeholder_tickers(tickers):
            return JSONResponse(
                status_code=500,
                content={"status": "error", "detail": "Universe unavailable"},
            )
    apply_limits = timeframe == "day"
    start_time = time.monotonic()
    processed = 0
    alerts_sent = 0
    for ticker in tickers:
        if universe_service.is_placeholder_ticker(ticker):
            logger.warning("Skipping placeholder ticker %s", ticker)
            continue
        if apply_limits and processed >= settings.max_tickers_per_run:
            logger.info("Stopping scan after hitting MAX_TICKERS_PER_RUN=%s", settings.max_tickers_per_run)
            break
        if apply_limits and (time.monotonic() - start_time) > settings.max_runtime_seconds:
            logger.info("Stopping scan after hitting runtime limit %ss", settings.max_runtime_seconds)
            break
        if apply_limits and alerts_sent >= settings.max_alerts_per_run:
            logger.info("Stopping scan after reaching MAX_ALERTS_PER_RUN=%s", settings.max_alerts_per_run)
            break
        if apply_limits:
            allowed, reason = allow_trade(session, ticker, mutate=False)
            if not allowed and reason:
                logger.info("Skipping %s due to governor: %s", ticker, reason)
                processed += 1
                continue
        candidate = _find_signal_for_ticker(ticker, client, settings.min_signal_score)
        if candidate:
            sig, scored = candidate
            signals.append((sig, scored.total))
        processed += 1
    if not signals:
        return {"message": "no signals"}
    if apply_limits and settings.max_alerts_per_run <= 0:
        logger.info("MAX_ALERTS_PER_RUN=%s prevents emitting alerts", settings.max_alerts_per_run)
        return {"message": "alerts capped for this run"}
    max_ideas = settings.ideas_per_run if apply_limits else len(signals)
    send_budget = min(settings.max_alerts_per_run, max_ideas)
    selected = sorted(signals, key=lambda x: x[1], reverse=True)[:send_budget]
    sent_signals: list[dict[str, object]] = []

    for signal, score in selected:
        allowed, reason = allow_trade(session, signal.ticker)
        if not allowed:
            logger.info("Skipping %s due to governor: %s", signal.ticker, reason)
            continue
        option_snapshot = client.get_options_chain_snapshot(signal.ticker)
        option_decision, underlying_price, market_open = _resolve_option_decision(
            signal, client, option_snapshot, settings
        )
        last_price = underlying_price
        if last_price is None and not market_open:
            last_price = get_maintenance_price(signal.ticker, client)
        if last_price is None:
            last_price = signal.entry_trigger
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
        send_result = send_or_log(
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
        try:
            trade = create_trade(
                session,
                signal,
                option_symbol=option_decision.contract.get("symbol") if option_decision.contract else None,
                entry_price=last_price,
                entry_mode=settings.entry_mode,
                timeframe=timeframe,
                telegram_msg_ids=[send_result.get("message_id")]
                if send_result.get("message_id")
                else None,
            )
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            logger.exception(
                "Failed to create trade for ticker=%s timeframe=%s: %s", signal.ticker, timeframe, exc
            )
            continue
        if settings.entry_mode == "immediate" and getattr(trade, "_was_created", False):
            in_message = format_im_in(trade)
            in_send_result = send_or_log(
                in_message,
                context={
                    "endpoint": f"/scan/{timeframe}",
                    "ticker": signal.ticker,
                    "request_id": request_id,
                    "alert_type": "IN",
                },
            )
            message_id = in_send_result.get("message_id")
            if message_id:
                current_ids = list(trade.telegram_msg_ids_json or [])
                current_ids.append(str(message_id))
                trade.telegram_msg_ids_json = current_ids
            record_trade_event(
                session,
                ticker=signal.ticker,
                instrument_type=instrument_type,
                side="in",
                payload={"message": in_message, "reason": "immediate entry"},
            )
        alerts_sent += 1
        sent_signals.append({"ticker": signal.ticker, "score": score})
        if apply_limits and alerts_sent >= send_budget:
            break
    return {"signals": sent_signals, "alerts_sent": alerts_sent, "limit": send_budget}


@app.post("/scan/{tf}")
def scan(tf: str, request: Request):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    session = SessionLocal()
    if tf not in {"scalp", "day", "swing"}:
        session.close()
        raise HTTPException(400, "invalid timeframe")
    logger.info("JOB START /scan/%s", tf)
    try:
        result = run_scan(tf, session, request.headers.get("x-request-id"))
        session.commit()
        logger.info("JOB END /scan/%s result=%s", tf, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /scan/%s", tf)
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )
    finally:
        session.close()


@app.get("/debug/db/schema")
def debug_db_schema(request: Request):
    if not _debug_endpoints_enabled():
        raise HTTPException(403, "debug endpoints disabled")
    schema = describe_trades_schema(engine)
    return {
        "table_exists": schema.get("table_exists", False),
        "columns": schema.get("columns", []),
        "last_migration": get_last_migration_result(),
    }


@app.get("/debug/explain")
def debug_explain(ticker: str, request: Request, session=Depends(get_session)):
    if not settings.debug_endpoints_enabled:
        raise HTTPException(403, "debug endpoints disabled")
    logger.info(
        "HIT method=%s path=%s user_agent=%s ticker=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
        ticker,
    )
    client = MassiveClient()
    try:
        bars = _load_bars_for_ticker(ticker, client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load bars for /debug/explain")
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})

    best_candidate = None
    best_score = float("-inf")
    qualified = None
    for detector in _detectors():
        sig = detector.detect(bars)
        if not sig:
            continue
        scored = score_signal(sig)
        sig.features["score"] = scored.total
        if scored.total >= settings.min_signal_score and qualified is None:
            qualified = (sig, scored)
        if scored.total > best_score:
            best_candidate = (sig, scored)
            best_score = scored.total

    selected = qualified or best_candidate
    governor_reason = None
    if selected:
        allowed, reason = allow_trade(session, ticker, mutate=False)
        if not allowed:
            governor_reason = reason
        summary, top_features, failed_gates = _summarize_candidate(
            selected[0], selected[1], settings.min_signal_score, governor_reason
        )
    else:
        summary = None
        top_features = []
        failed_gates = ["No detectors triggered"]

    if not selected:
        failed_gates.append("Score below threshold" if best_score > float("-inf") else "No score computed")
    elif selected[1].total < settings.min_signal_score:
        failed_gates.append(f"Below MIN_SIGNAL_SCORE {settings.min_signal_score}")

    response = {
        "ticker": ticker,
        "bar_count": len(bars),
        "last_price": bars[-1].get("close") if bars else None,
        "best_candidate": summary,
        "top_features_used": top_features,
        "failed_gates": failed_gates,
        "timestamp_et": format_et_timestamp(),
    }
    logger.info("JOB END /debug/explain result=%s", response)
    return response


@app.get("/debug/universe")
def debug_universe(session=Depends(get_session)):
    if not settings.debug_endpoints_enabled:
        raise HTTPException(403, "debug endpoints disabled")
    tickers = universe_service.latest_universe(session)
    return {
        "count": len(tickers),
        "sample": tickers[:20],
        "contains_fillers": universe_service.contains_placeholder_tickers(tickers),
    }


@app.get("/debug/open-trades")
def debug_open_trades(session=Depends(get_session)):
    if not settings.debug_endpoints_enabled:
        raise HTTPException(403, "debug endpoints disabled")
    trades = session.query(models.Trade).filter(models.Trade.status == "OPEN").all()
    sample = [
        {
            "ticker": trade.ticker,
            "status": trade.status,
            "opened_at": trade.opened_at,
            "entry_price": trade.entry_price,
            "entry_trigger_price": trade.entry_trigger_price,
            "stop_price": trade.stop_price,
            "target_prices": trade.target_prices,
            "last_price": trade.last_price,
        }
        for trade in trades[:50]
    ]
    return {"count": len(trades), "sample": sample}


@app.post("/debug/force-entry")
def debug_force_entry(ticker: str, request: Request, session=Depends(get_session)):
    if not settings.debug_endpoints_enabled:
        raise HTTPException(403, "debug endpoints disabled")

    ticker = ticker.upper()
    logger.info(
        "HIT method=%s path=%s user_agent=%s ticker=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
        ticker,
    )

    trade = (
        session.query(models.Trade)
        .filter(models.Trade.ticker == ticker, models.Trade.status == "PENDING")
        .order_by(models.Trade.opened_at.desc())
        .first()
    )
    if not trade:
        raise HTTPException(404, "no pending trade found")

    client = MassiveClient()
    snapshot = client.get_snapshot(ticker) or {}
    entry_price = snapshot.get("last") or trade.entry_trigger_price or trade.entry_trigger
    if entry_price is None:
        raise HTTPException(400, "no price available for ticker")

    trade.entry_price = entry_price
    trade.last_price = entry_price
    trade.status = "OPEN"
    trade.opened_at = datetime.utcnow()
    session.commit()
    session.refresh(trade)

    logger.info(
        "TRADE TRANSITION ticker=%s from=PENDING to=OPEN reason=debug_force_entry",
        trade.ticker,
    )

    in_msg = format_im_in(trade)
    send_or_log(
        in_msg,
        context={"endpoint": "/debug/force-entry", "ticker": ticker, "alert_type": "IN"},
    )
    record_trade_event(
        session,
        ticker=ticker,
        instrument_type=_instrument_type_from_trade(trade),
        side="in",
        payload={"message": in_msg, "reason": "debug_force_entry"},
    )
    session.commit()
    return {"status": "ok", "ticker": ticker, "entry_price": entry_price}


@app.post("/debug/force-exit")
def debug_force_exit(
    ticker: str,
    request: Request,
    reason: str = "manual",
    session=Depends(get_session),
):
    if not settings.debug_endpoints_enabled:
        raise HTTPException(403, "debug endpoints disabled")

    ticker = ticker.upper()
    logger.info(
        "HIT method=%s path=%s user_agent=%s ticker=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
        ticker,
    )

    trade = (
        session.query(models.Trade)
        .filter(models.Trade.ticker == ticker, models.Trade.status == "OPEN")
        .order_by(models.Trade.opened_at.desc())
        .first()
    )
    if not trade:
        raise HTTPException(404, "no open trade found")

    client = MassiveClient()
    snapshot = client.get_snapshot(ticker) or {}
    last_price = snapshot.get("last") or trade.last_price or trade.entry_price
    trade.last_price = last_price
    trade.status = "CLOSED"
    trade.exit_reason = reason or "manual"
    trade.closed_at = datetime.utcnow()
    session.commit()
    session.refresh(trade)

    logger.info(
        "TRADE TRANSITION ticker=%s from=OPEN to=CLOSED reason=%s",
        trade.ticker,
        trade.exit_reason,
    )

    out_msg = format_im_out(trade)
    send_or_log(
        out_msg,
        context={"endpoint": "/debug/force-exit", "ticker": ticker, "alert_type": "OUT"},
    )
    record_trade_event(
        session,
        ticker=ticker,
        instrument_type=_instrument_type_from_trade(trade),
        side="out",
        payload={"message": out_msg, "reason": trade.exit_reason},
    )
    session.commit()
    return {"status": "ok", "ticker": ticker, "exit_reason": trade.exit_reason, "last_price": last_price}


@app.post("/debug/close-all-trades")
def debug_close_all_trades(
    request: Request,
    reason: str = "manual-reset",
    send_alerts: bool = False,
    session=Depends(get_session),
):
    if not settings.debug_endpoints_enabled:
        raise HTTPException(403, "debug endpoints disabled")
    trades = session.query(models.Trade).filter(models.Trade.status == "OPEN").all()
    messages = []
    now = datetime.utcnow()
    for trade in trades:
        trade.status = "CLOSED"
        trade.exit_reason = reason
        trade.closed_at = now
        if send_alerts:
            out_msg = format_im_out(trade)
            send_or_log(
                out_msg,
                context={"endpoint": "/debug/close-all-trades", "ticker": trade.ticker, "alert_type": "OUT"},
            )
            messages.append(out_msg)
    session.commit()
    return {"closed": len(trades), "messages_sent": len(messages)}


@app.post("/state/update")
def state_update(request: Request):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /state/update")
    session = SessionLocal()
    client = MassiveClient()

    def price_lookup(ticker: str):
        return get_maintenance_price(ticker, client)
    try:
        tickers = universe_service.build_universe(session, client=client)
        entries, exits = update_trade_states(session, price_lookup, settings=settings)
        messages = 0
        for entry in entries:
            in_msg = format_im_in(entry)
            send_or_log(
                in_msg,
                context={"endpoint": "/state/update", "ticker": entry.ticker, "alert_type": "IN"},
            )
            record_trade_event(
                session,
                ticker=entry.ticker,
                instrument_type=_instrument_type_from_trade(entry),
                side="in",
                payload={"message": in_msg, "reason": "triggered"},
            )
            messages += 1

        for exit in exits:
            out_msg = format_im_out(exit)
            send_or_log(
                out_msg,
                context={"endpoint": "/state/update", "ticker": exit.ticker, "alert_type": "OUT"},
            )
            record_trade_event(
                session,
                ticker=exit.ticker,
                instrument_type=_instrument_type_from_trade(exit),
                side="out",
                payload={"message": out_msg, "reason": exit.exit_reason},
            )
            messages += 1
        session.commit()
        response = {
            "status": "ok",
            "universe_count": len(tickers),
            "updated_trades": len(entries) + len(exits),
            "entries": len(entries),
            "exits": len(exits),
            "messages": messages,
        }
        logger.info("JOB END /state/update result=%s", response)
        return response
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /state/update")
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )
    finally:
        session.close()


@app.get("/debug/trades")
def debug_trades(session=Depends(get_session)):
    if settings.env != "dev":
        raise HTTPException(403, "forbidden")
    trades = session.execute(text("SELECT ticker,state FROM trades")).fetchall()
    return {"trades": [dict(row) for row in trades]}


@app.get("/debug/trades/open")
def debug_open_trades(request: Request):
    if not _debug_endpoints_enabled():
        raise HTTPException(403, "debug endpoints disabled")

    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )

    try:
        with engine.connect() as connection:
            if not table_exists(connection, "trades"):
                return {"count": 0, "trades": [], "note": "trades-table-missing"}

            rows = connection.execute(
                text(
                    "SELECT id, ticker, status, opened_at, closed_at, exit_reason "
                    "FROM trades WHERE status = 'OPEN'"
                )
            ).mappings().all()
        return {"count": len(rows), "trades": [dict(row) for row in rows]}
    except Exception:  # noqa: BLE001
        logger.warning("DB unavailable for /debug/trades/open")
        return _db_unavailable_response()


@app.post("/debug/trades/reset")
def debug_reset_trades(
    request: Request,
    mode: str = "close_all",
    send_alerts: bool = False,
    session=Depends(get_session),
):
    if not _debug_endpoints_enabled():
        raise HTTPException(403, "debug endpoints disabled")

    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )

    if mode not in {"close_all", "close_stale"}:
        raise HTTPException(400, "invalid mode")

    try:
        connection = session.connection()
        if not table_exists(connection, "trades"):
            return {"status": "ok", "closed_count": 0, "note": "trades-table-missing"}
    except Exception:  # noqa: BLE001
        logger.warning("DB unavailable for /debug/trades/reset")
        return _db_unavailable_response()

    cutoff = None
    if mode == "close_stale":
        cutoff = datetime.utcnow() - timedelta(hours=float(settings.exit_max_hours_open))

    query = session.query(models.Trade).filter(models.Trade.status == "OPEN")
    if cutoff:
        query = query.filter(models.Trade.opened_at <= cutoff)

    trades = query.all()
    closed_count = 0
    messages_sent = 0
    now = datetime.utcnow()
    exit_reason = "reset-close-stale" if mode == "close_stale" else "reset-close-all"
    for trade in trades:
        trade.status = "CLOSED"
        trade.exit_reason = exit_reason
        trade.closed_at = now
        closed_count += 1
        if send_alerts:
            out_msg = format_im_out(trade)
            send_or_log(
                out_msg,
                context={
                    "endpoint": "/debug/trades/reset",
                    "ticker": trade.ticker,
                    "alert_type": "OUT",
                },
            )
            messages_sent += 1

    return {
        "status": "ok",
        "closed_count": closed_count,
        "messages_sent": messages_sent,
        "mode": mode,
    }


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
    send_preview: bool = False,
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

    preview_reasons: list[str] = []
    if not _within_rth():
        if not send_preview:
            return {"message": "outside RTH"}
        preview_reasons.append("Market closed (outside RTH)")

    used_threshold = float(min_score_override) if min_score_override is not None else settings.min_signal_score
    client = MassiveClient()

    try:
        candidate = _find_signal_for_ticker(
            ticker, client, used_threshold, return_best=send_preview
        )
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
    timeframe = (getattr(signal, "timeframe", None) or "day").strip() or "day"
    qualifies_normally = scored.total >= used_threshold
    reasons = _top_reasons(scored)

    option_snapshot = client.get_options_chain_snapshot(signal.ticker)
    option_decision, _, _ = _resolve_option_decision(
        signal, client, option_snapshot, settings
    )
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

    failure_reasons = preview_reasons.copy()
    if not qualifies_normally:
        failure_reasons.append(
            f"Score below threshold ({scored.total:.1f} < {used_threshold})"
        )

    mutate_governor = not (send_preview and (not qualifies_normally or preview_reasons))
    allowed, reason = allow_trade(session, signal.ticker, mutate=mutate_governor)
    if not allowed and reason:
        failure_reasons.append(reason)
    if not allowed and not send_preview:
        response_payload.update({"status": "blocked", "detail": reason})
        logger.info("JOB END /debug/force-alert result=%s", response_payload)
        return JSONResponse(status_code=429, content=response_payload)

    should_send_preview = send_preview and (not qualifies_normally or not allowed or preview_reasons)

    if should_send_preview:
        snapshot = client.get_snapshot(signal.ticker) or {}
        underlying_price = snapshot.get("last") or signal.entry_trigger
        preview_context = {
            "endpoint": "/debug/force-alert",
            "ticker": signal.ticker,
            "request_id": request.headers.get("x-request-id"),
            "preview": True,
        }
        header_lines = [
            "🧪 PREVIEW ALERT (NOT A LIVE TRADE)",
            f"Reason: {failure_reasons[0] if failure_reasons else 'Unknown'}",
            f"Ticker: {signal.ticker}",
            f"Underlying: {underlying_price}",
            f"Score: {scored.total:.1f}",
            f"Used threshold: {used_threshold}",
            "Failed gates:"
            + ("\n" + "\n".join(f"- {r}" for r in failure_reasons[:3]) if failure_reasons else " none"),
            f"Timestamp: {format_et_timestamp()}",
            "",
        ]
        preview_message = "\n".join(header_lines) + message
        send_result = send_or_log(preview_message, context=preview_context)
        response_payload.update(
            {
                "status": "sent_preview" if send_result.get("ok") else "error",
                "telegram_status_code": send_result.get("status_code"),
                "qualified": False,
                "top_failed_gates": failure_reasons[:3],
            }
        )
        logger.info("JOB END /debug/force-alert result=%s", response_payload)
        return response_payload

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
    try:
        create_trade(
            session,
            signal,
            option_symbol=option_decision.contract.get("symbol") if option_decision.contract else None,
            timeframe=timeframe,
            telegram_msg_ids=[send_result.get("message_id")]
            if send_result.get("message_id")
            else None,
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception(
            "Failed to create trade for ticker=%s timeframe=%s from /debug/force-alert: %s",
            signal.ticker,
            timeframe,
            exc,
        )

    response_payload.update(
        {
            "status": "sent" if send_result.get("ok") else "error",
            "telegram_status_code": send_result.get("status_code"),
        }
    )
    logger.info("JOB END /debug/force-alert result=%s", response_payload)
    return response_payload


@app.post("/debug/preview-alert")
def debug_preview_alert(ticker: str, request: Request):
    if os.getenv("DEBUG_ENDPOINTS_ENABLED", "false").lower() != "true":
        raise HTTPException(403, "forbidden")

    ticker = ticker.upper()
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /debug/preview-alert ticker=%s", ticker)

    client = MassiveClient()
    try:
        candidate = _find_signal_for_ticker(
            ticker, client, settings.min_signal_score, return_best=True
        )
    except ValueError as exc:
        logger.exception("JOB ERROR /debug/preview-alert")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("JOB ERROR /debug/preview-alert")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )

    market_open = is_rth_now(settings)
    option_snapshot = client.get_options_chain_snapshot(ticker)
    underlying_price = (
        get_execution_price(ticker, client)
        if market_open
        else get_maintenance_price(ticker, client)
    )

    header_lines = [
        "🧪 PREVIEW ALERT (NOT A LIVE TRADE)",
        f"Ticker: {ticker}",
        f"Snapshot price: {underlying_price if underlying_price is not None else '-'}",
    ]

    message_body = "No setups qualified on the latest data."
    preview_context = {
        "endpoint": "/debug/preview-alert",
        "ticker": ticker,
        "request_id": request.headers.get("x-request-id"),
        "preview": True,
    }

    if candidate:
        signal, scored = candidate
        qualified_normally = scored.total >= settings.min_signal_score
        header_lines.extend(
            [
                f"Signal score: {scored.total:.1f}",
                f"Threshold: {settings.min_signal_score}",
                f"Qualified normally: {'yes' if qualified_normally else 'no'}",
            ]
        )

        option_decision, _, _ = _resolve_option_decision(
            signal, client, option_snapshot, settings
        )
        logger.info(
            "Option decision for %s chosen=%s reason=%s",
            signal.ticker,
            bool(option_decision.contract),
            option_decision.reason,
        )
        if option_decision.contract:
            message_body = format_trade_idea_with_options(signal, option_decision.contract)
        else:
            stock_reasons = option_decision.fallback_reasons or [
                "Options premiums elevated or expensive",
                "Spread/liquidity not ideal",
                "Cleaner risk with shares",
            ]
            message_body = format_trade_idea_stock_only(signal, stock_reasons)
    else:
        logger.info("No setups qualified for %s", ticker)

    header_lines.append(f"Timestamp: {format_et_timestamp()}")
    preview_message = "\n".join(header_lines + ["", message_body])
    send_result = send_or_log(preview_message, context=preview_context)

    if not send_result.get("ok"):
        response = {
            "status": "error",
            "ticker": ticker,
            "telegram_status_code": send_result.get("status_code"),
            "detail": send_result.get("response"),
        }
        logger.error("JOB ERROR /debug/preview-alert result=%s", response)
        return JSONResponse(status_code=500, content=response)

    response = {"status": "sent_preview", "ticker": ticker}
    logger.info("JOB END /debug/preview-alert result=%s", response)
    return response
