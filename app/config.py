import os
from datetime import datetime, time
from functools import lru_cache
from datetime import datetime, time
import os

import pytz
from dotenv import load_dotenv


load_dotenv()


def _parse_float(value: str | None, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Settings:
    env: str = os.getenv("ENV", "dev")
    timezone: str = os.getenv("TIMEZONE", "America/New_York")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./local.db")
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    db_auto_migrate: bool = os.getenv("DB_AUTO_MIGRATE", "true").lower() == "true"

    massive_api_key: str = os.getenv("MASSIVE_API_KEY", "demo")
    massive_base_url: str = os.getenv("MASSIVE_BASE_URL", "https://api.polygon.io")

    universe_size: int = int(os.getenv("UNIVERSE_SIZE", "20"))
    always_include_tickers: list[str] = [
        t.strip()
        for t in os.getenv(
            "ALWAYS_INCLUDE_TICKERS",
            "SPY,QQQ,IWM,DIA,XLK,XLF,XLV,XLE,XLI,XLY,XLP,XLU,XLB,XLC,XBI,SMH",
        ).split(",")
        if t.strip()
    ]
    exclude_tickers: list[str] = [t.strip() for t in os.getenv("EXCLUDE_TICKERS", "").split(",") if t.strip()]

    enable_rth_only: bool = os.getenv("ENABLE_RTH_ONLY", "true").lower() == "true"
    rth_start: str = os.getenv("RTH_START", "09:30")
    rth_end: str = os.getenv("RTH_END", "16:00")

    max_tickers_per_run: int = int(os.getenv("MAX_TICKERS_PER_RUN", "250"))
    max_runtime_seconds: int = int(os.getenv("MAX_RUNTIME_SECONDS", "40"))
    max_alerts_per_run: int = int(os.getenv("MAX_ALERTS_PER_RUN", "3"))
    ideas_per_run: int = int(os.getenv("IDEAS_PER_RUN", "3"))
    alert_cooldown_minutes: int = int(
        os.getenv("ALERT_COOLDOWN_MINUTES", os.getenv("TICKER_COOLDOWN_MINUTES", "15"))
    )

    min_signal_score: float = None  # type: ignore[assignment]
    cooldown_minutes: int = int(os.getenv("COOLDOWN_MINUTES", "30"))
    max_alerts_per_ticker_per_day: int = int(os.getenv("MAX_ALERTS_PER_TICKER_PER_DAY", "3"))

    options_enabled: bool = os.getenv("OPTIONS_ENABLED", "true").lower() == "true"
    options_only_if_score_at_least: int = int(os.getenv("OPTIONS_ONLY_IF_SCORE_AT_LEAST", "82"))

    dte_scalp_min: int = int(os.getenv("DTE_SCALP_MIN", "0"))
    dte_scalp_max: int = int(os.getenv("DTE_SCALP_MAX", "30"))
    dte_day_min: int = int(os.getenv("DTE_DAY_MIN", "3"))
    dte_day_max: int = int(os.getenv("DTE_DAY_MAX", "30000"))
    dte_swing_min: int = int(os.getenv("DTE_SWING_MIN", "14"))
    dte_swing_max: int = int(os.getenv("DTE_SWING_MAX", "30000"))
    delta_scalp_min: float = float(os.getenv("DELTA_SCALP_MIN", "0.30"))
    delta_scalp_max: float = float(os.getenv("DELTA_SCALP_MAX", "0.45"))
    delta_day_min: float = float(os.getenv("DELTA_DAY_MIN", "0.35"))
    delta_day_max: float = float(os.getenv("DELTA_DAY_MAX", "0.55"))
    delta_swing_min: float = float(os.getenv("DELTA_SWING_MIN", "0.45"))
    delta_swing_max: float = float(os.getenv("DELTA_SWING_MAX", "0.65"))

    min_oi: int = int(os.getenv("MIN_OI", "500"))
    min_option_volume: int = int(os.getenv("MIN_OPTION_VOLUME", "50"))
    max_bid_ask_spread_pct: float = float(os.getenv("MAX_BID_ASK_SPREAD_PCT", "0.25"))
    max_bid_ask_spread_abs: float = float(os.getenv("MAX_BID_ASK_SPREAD_ABS", "1.00"))

    opt_max_moneyness_pct: float = float(os.getenv("OPT_MAX_MONEYNESS_PCT", "0.12"))
    opt_max_spread_pct: float = float(os.getenv("OPT_MAX_SPREAD_PCT", "0.20"))
    opt_min_dte: int = int(os.getenv("OPT_MIN_DTE", "5"))
    opt_max_dte: int = int(os.getenv("OPT_MAX_DTE", "21"))
    opt_min_volume: int = int(os.getenv("OPT_MIN_VOLUME", "50"))
    opt_min_oi: int = int(os.getenv("OPT_MIN_OI", "200"))
    opt_call_delta_min: float = float(os.getenv("OPT_CALL_DELTA_MIN", "0.20"))
    opt_call_delta_max: float = float(os.getenv("OPT_CALL_DELTA_MAX", "0.55"))
    opt_put_delta_min: float = float(os.getenv("OPT_PUT_DELTA_MIN", "-0.55"))
    opt_put_delta_max: float = float(os.getenv("OPT_PUT_DELTA_MAX", "-0.20"))

    max_premium_scalp: float = float(os.getenv("MAX_PREMIUM_SCALP", "0.80"))
    max_premium_day: float = float(os.getenv("MAX_PREMIUM_DAY", "2.50"))
    max_premium_swing: float = float(os.getenv("MAX_PREMIUM_SWING", "6.00"))
    max_premium_pct_underlying_day: float = float(os.getenv("MAX_PREMIUM_PCT_UNDERLYING_DAY", "0.004"))
    max_breakeven_vs_target_mult: float = float(os.getenv("MAX_BREAKEVEN_VS_TARGET_MULT", "1.25"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "demo")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "demo")
    telegram_enabled: bool = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    alerts_enabled: bool = os.getenv("ALERTS_ENABLED", "true").lower() == "true"
    alert_style: str = os.getenv("ALERT_STYLE", "medium")
    alert_mode: str = os.getenv("ALERT_MODE", "ideas")
    enable_follow_up_alerts: bool = os.getenv("ENABLE_FOLLOW_UP_ALERTS", "false").lower() == "true"
    debug_endpoints_enabled: bool = os.getenv("DEBUG_ENDPOINTS_ENABLED", "false").lower() == "true"
    entry_mode: str = os.getenv("ENTRY_MODE", "confirm").lower()
    exit_max_hours_open: float = float(os.getenv("EXIT_MAX_HOURS_OPEN", "6"))
    exit_stop_atr_mult: float = float(os.getenv("EXIT_STOP_ATR_MULT", "1.5"))
    exit_target_r_mult_1: float = float(os.getenv("EXIT_TARGET_R_MULT_1", "1.0"))
    exit_target_r_mult_2: float = float(os.getenv("EXIT_TARGET_R_MULT_2", "2.0"))
    exit_trail_after_r: float = float(os.getenv("EXIT_TRAIL_AFTER_R", "1.0"))
    exit_trail_pct: float = float(os.getenv("EXIT_TRAIL_PCT", "0.6"))


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.min_signal_score = _parse_float(
        os.getenv("MIN_SIGNAL_SCORE"),
        _parse_float(os.getenv("MIN_SCORE_DAY"), 78.0),
    )
    return settings


def _parse_time(value: str) -> time:
    hour, minute = [int(part) for part in value.split(":", maxsplit=1)]
    return time(hour=hour, minute=minute)


def is_rth_now(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    tz = pytz.timezone(settings.timezone)
    now = datetime.now(tz)
    start = tz.localize(datetime.combine(now.date(), _parse_time(settings.rth_start)))
    end = tz.localize(datetime.combine(now.date(), _parse_time(settings.rth_end)))
    return start <= now <= end
