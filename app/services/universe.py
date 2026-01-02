from datetime import date
from typing import List
from app.config import get_settings
from app.models import Universe


def build_universe(session) -> List[str]:
    settings = get_settings()
    # Basic deterministic universe: always include configured tickers and append placeholders
    tickers = list(dict.fromkeys(settings.always_include_tickers))
    # Fill to universe_size with synthetic tickers for tests
    while len(tickers) < settings.universe_size:
        tickers.append(f"T{len(tickers)+1}")
    today = date.today().isoformat()
    record = Universe(date=today, tickers_json=tickers)
    session.add(record)
    session.commit()
    return tickers


def latest_universe(session) -> List[str]:
    record = session.query(Universe).order_by(Universe.created_at.desc()).first()
    return record.tickers_json if record else []
