from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.utils.dates import format_et_timestamp, normalize_any_date_to_mmddyyyy, parse_mmddyyyy


def _fmt_price(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_percent(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_int(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{int(value)}"
    except (TypeError, ValueError):
        return str(value)


def _resolve_expiration(contract: Dict[str, Any]) -> tuple[str, Optional[datetime]]:
    raw_exp = contract.get("expiration_iso") or contract.get("expiration")
    if not raw_exp:
        details = contract.get("details") or {}
        raw_exp = details.get("expiration_date")
    if not raw_exp:
        return "-", None
    try:
        normalized = normalize_any_date_to_mmddyyyy(str(raw_exp))
        exp_date = parse_mmddyyyy(normalized)
        return exp_date.strftime("%m-%d-%Y"), exp_date
    except Exception:
        return str(raw_exp), None


def _contract_fields(contract: Dict[str, Any]) -> Dict[str, Any]:
    details = contract.get("details") or {}
    last_quote = contract.get("last_quote") or {}
    day = contract.get("day") or {}

    bid = contract.get("bid", last_quote.get("bid"))
    ask = contract.get("ask", last_quote.get("ask"))
    mid = contract.get("mid") or last_quote.get("midpoint")
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2

    spread_pct = None
    if bid is not None and ask is not None and mid:
        try:
            spread_pct = (ask - bid) / mid if mid != 0 else None
        except Exception:  # noqa: BLE001
            spread_pct = None

    expiration_text, exp_date = _resolve_expiration(contract)
    contract_type_raw = contract.get("type") or contract.get("option_type") or details.get("contract_type")
    contract_type = (contract_type_raw or "").upper()
    call_put = "CALL" if contract_type.startswith("C") or contract_type == "CALL" else "PUT"

    return {
        "symbol": contract.get("symbol") or details.get("ticker"),
        "strike": contract.get("strike") or details.get("strike_price"),
        "expiration_text": expiration_text,
        "expiration_date": exp_date,
        "contract_type": call_put,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "open_interest": contract.get("open_interest"),
        "volume": contract.get("volume") or day.get("volume"),
        "underlying_price": contract.get("underlying_price"),
    }


def _timestamp(dt: Optional[datetime] = None) -> str:
    return format_et_timestamp(dt)


def _reasons(reasons: Iterable[str], limit: int = 3) -> List[str]:
    filtered = [reason for reason in reasons if reason]
    if not filtered:
        return []
    return filtered[:limit]


def render_stock_alert(payload: Dict[str, Any]) -> str:
    ticker = payload.get("ticker", "-")
    bias = payload.get("bias", "Bullish").title()
    market_context = payload.get("market_context") or "setup"
    trigger = _fmt_price(payload.get("trigger"))
    invalidation = _fmt_price(payload.get("invalidation"))
    targets = payload.get("targets") or []
    t1 = _fmt_price(targets[0]) if len(targets) > 0 else "-"
    t2 = _fmt_price(targets[1]) if len(targets) > 1 else "-"
    reasons = _reasons(payload.get("reasons", []), limit=3)
    confidence = payload.get("confidence") or "-"
    if not reasons:
        reasons = [
            "Options premiums elevated or expensive",
            "Spread/liquidity not ideal",
            "Cleaner risk with shares",
        ]
    execution_plan = payload.get("execution_plan") or "Respect the plan and size appropriately."
    ts = _timestamp(payload.get("timestamp"))

    lines = [
        f"📌 IDEA ALERT — {ticker} (STOCK)",
        f"Bias: {bias}",
        f"Trigger: {trigger}",
        f"Invalidation: {invalidation}",
        f"Targets: {t1} → {t2}",
        f"Confidence: {confidence}/10",
        "",
        f"Context: {market_context}",
        "Rationale:",
        *[f"• {reason}" for reason in reasons],
        "",
        "Plan:",
        execution_plan,
        "",
        f"Timestamp: {ts}",
    ]
    return "\n".join(lines)


def render_option_alert(payload: Dict[str, Any]) -> str:
    ticker = payload.get("ticker", "-")
    setup = payload.get("setup") or "setup"
    bias = payload.get("bias", "Bullish").title()
    confidence_raw = payload.get("confidence")
    try:
        confidence = round(float(confidence_raw), 1)
    except Exception:  # noqa: BLE001
        confidence = confidence_raw or "-"

    underlying_price = _fmt_price(payload.get("underlying_price"))
    contract_fields = _contract_fields(payload.get("contract", {}))
    contract_ticker = contract_fields.get("symbol") or ticker
    strike = _fmt_price(contract_fields.get("strike"))
    contract_type = contract_fields.get("contract_type") or (payload.get("instrument_type") or "CALL").upper()
    expiration = contract_fields.get("expiration_text")
    mid = _fmt_price(contract_fields.get("mid"))
    bid = _fmt_price(contract_fields.get("bid"))
    ask = _fmt_price(contract_fields.get("ask"))
    oi = _fmt_int(contract_fields.get("open_interest"))
    vol = _fmt_int(contract_fields.get("volume"))
    spread_pct_val = contract_fields.get("spread_pct")
    spread_pct = _fmt_percent(spread_pct_val * 100 if isinstance(spread_pct_val, (int, float)) else spread_pct_val)

    plan = payload.get("plan", {})
    trigger = _fmt_price(plan.get("entry") or payload.get("trigger"))
    invalidation = plan.get("stop") or plan.get("risk_rule") or payload.get("invalidation")
    invalidation_text = invalidation if isinstance(invalidation, str) else _fmt_price(invalidation)
    targets = plan.get("targets") or []
    t1 = _fmt_price(targets[0]) if len(targets) > 0 else _fmt_price(plan.get("t1"))
    t2 = _fmt_price(targets[1]) if len(targets) > 1 else _fmt_price(plan.get("t2"))
    notes = plan.get("notes") or payload.get("notes") or "Respect stops and liquidity."

    ts = _timestamp(payload.get("timestamp"))

    lines = [
        f"📌 IDEA ALERT — {ticker} ({contract_type})",
        f"Bias: {bias}",
        f"Trigger: {trigger}",
        f"Invalidation: {invalidation_text}",
        f"Targets: {t1} → {t2}",
        f"Confidence: {confidence}/10",
        "",
        f"Context: {setup}",
        f"Underlying: {underlying_price}",
        "Contract:",
        f"• {contract_ticker} {strike}{contract_type[0].upper() if contract_type else ''}",
        f"• Exp: {expiration}",
        f"• Mid: {mid}",
        f"• Bid/Ask: {bid} / {ask}",
        f"• OI/Vol: {oi} / {vol}",
        f"• Spread: {spread_pct}%",
        "",
        "Notes:",
        notes,
        "",
        f"Timestamp: {ts}",
    ]
    return "\n".join(lines)


def render_in_alert(payload: Dict[str, Any]) -> str:
    ticker = payload.get("ticker", "-")
    instrument_type = (payload.get("instrument_type") or "STOCK").upper()
    fill = _fmt_price(payload.get("fill_price"))
    stop_price = _fmt_price(payload.get("stop_price"))
    plan = payload.get("plan") or "Follow the plan and keep sizing disciplined."
    ts = _timestamp(payload.get("timestamp"))

    lines = [
        f"✅ I'M IN — {ticker} ({instrument_type})",
        f"Entry: {fill}",
        f"Risk guardrail: {stop_price}",
        f"Plan: {plan}",
        f"Timestamp: {ts}",
    ]
    return "\n".join(lines)


def render_out_alert(payload: Dict[str, Any]) -> str:
    ticker = payload.get("ticker", "-")
    instrument_type = (payload.get("instrument_type") or "STOCK").upper()
    exit_price = _fmt_price(payload.get("exit_price"))
    pnl_pct_raw = payload.get("pnl_pct")
    pnl_abs_raw = payload.get("pnl_abs")
    pnl_pct = _fmt_percent(pnl_pct_raw)
    pnl_abs = _fmt_price(pnl_abs_raw) if pnl_abs_raw is not None else None
    reason = payload.get("reason") or "target hit"
    ts = _timestamp(payload.get("timestamp"))

    result_line = f"Result: {pnl_pct}%"
    if pnl_abs is not None and pnl_abs != "-":
        result_line = f"Result: {pnl_pct}% ({pnl_abs})"

    lines = [
        f"🏁 I'M OUT — {ticker} ({instrument_type})",
        f"Exit: {exit_price}",
        result_line,
        f"Reason: {reason}",
        f"Timestamp: {ts}",
    ]
    return "\n".join(lines)
