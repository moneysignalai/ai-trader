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
from app.services.feature_enricher import enrich_bars
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


def _ideas_mode_active() -> bool:
    return (getattr(settings, "alert_mode", "ideas") or "ideas").lower() == "ideas"


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
        return "CALL" if getattr(trade, "direction", "bull") == "bull" else "PUT"
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
        alerts_sent += 1
        sent_signals.append({"ticker": signal.ticker, "score": score})
        if apply_limits and alerts_sent >= send_budget:
            break
    return {"signals": sent_signals, "alerts_sent": alerts_sent, "limit": send_budget}


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


@app.post("/state/update")
def state_update(request: Request, session=Depends(get_session)):
    logger.info(
        "HIT method=%s path=%s user_agent=%s",
        request.method,
        request.url.path,
        request.headers.get("user-agent"),
    )
    logger.info("JOB START /state/update")
    client = MassiveClient()

    def price_lookup(ticker: str):
        snap = client.get_snapshot(ticker)
        return snap.get("last", 0) or 0
    try:
        tickers = universe_service.build_universe(session, client=client)
        updated = update_trade_states(session, price_lookup)
        response = {
            "status": "ok",
            "universe_count": len(tickers),
            "updated_trades": len(updated),
            "messages": 0,
        }
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
    qualifies_normally = scored.total >= used_threshold
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

    snapshot = client.get_snapshot(ticker) or {}
    option_snapshot = client.get_options_chain_snapshot(ticker)
    underlying_price = snapshot.get("last")

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

        option_decision = select_option(
            signal, option_snapshot, underlying_price=underlying_price or signal.entry_trigger
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
