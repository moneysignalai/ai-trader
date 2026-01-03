import os
from datetime import datetime, time
from functools import lru_cache

import pytz
from dotenv import load_dotenv


load_dotenv()


class Settings:
    env: str = os.getenv("ENV", "dev")
    timezone: str = os.getenv("TIMEZONE", "America/New_York")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./local.db")
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    massive_api_key: str = os.getenv("MASSIVE_API_KEY", "demo")
    massive_base_url: str = os.getenv("MASSIVE_BASE_URL", "https://api.polygon.io")

    universe_size: int = int(os.getenv("UNIVERSE_SIZE", "20"))
    always_include_tickers: list[str] = os.getenv(
        "ALWAYS_INCLUDE_TICKERS",
        "SPY,QQQ,IWM,DIA,XLK,XLF,XLV,XLE,XLI,XLY,XLP,XLU,XLB,XLC,XBI,SMH",
    ).split(",")
    exclude_tickers: list[str] = [t for t in os.getenv("EXCLUDE_TICKERS", "").split(",") if t]

    enable_rth_only: bool = os.getenv("ENABLE_RTH_ONLY", "true").lower() == "true"
    rth_start: str = os.getenv("RTH_START", "09:30")
    rth_end: str = os.getenv("RTH_END", "16:00")

    min_score_scalp: int = int(os.getenv("MIN_SCORE_SCALP", "80"))
    min_score_day: int = int(os.getenv("MIN_SCORE_DAY", "78"))
    min_score_swing: int = int(os.getenv("MIN_SCORE_SWING", "75"))
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

    max_premium_scalp: float = float(os.getenv("MAX_PREMIUM_SCALP", "0.80"))
    max_premium_day: float = float(os.getenv("MAX_PREMIUM_DAY", "2.50"))
    max_premium_swing: float = float(os.getenv("MAX_PREMIUM_SWING", "6.00"))
    max_premium_pct_underlying_day: float = float(os.getenv("MAX_PREMIUM_PCT_UNDERLYING_DAY", "0.004"))
    max_breakeven_vs_target_mult: float = float(os.getenv("MAX_BREAKEVEN_VS_TARGET_MULT", "1.25"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "demo")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "demo")
    telegram_disable: bool = os.getenv("TELEGRAM_DISABLE", "true").lower() == "true"
    alerts_enabled: bool = os.getenv("ALERTS_ENABLED", "true").lower() == "true"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


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
