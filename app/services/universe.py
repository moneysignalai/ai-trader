from datetime import date, timedelta
from typing import List

from app.config import get_settings
from app.models import Universe
from app.services.massive_client import MassiveClient


def _fetch_top_volume(client: MassiveClient, target_date: date) -> List[str]:
    tickers = client.get_top_volume(target_date.isoformat())
    return [t for t in tickers if t]


def build_universe(session) -> List[str]:
    settings = get_settings()
    client = MassiveClient()
    today = date.today()
    # try today then previous trading day fallback
    tickers = _fetch_top_volume(client, today)
    if len(tickers) < settings.universe_size:
        tickers = _fetch_top_volume(client, today - timedelta(days=1))

    tickers = [t for t in tickers if t not in settings.exclude_tickers]
    tickers = list(dict.fromkeys(settings.always_include_tickers + tickers))
    tickers = tickers[: max(settings.universe_size, 500)]
    if len(tickers) < 500:
        # pad deterministically if provider returned fewer
        while len(tickers) < 500:
            tickers.append(f"FILL{len(tickers)+1}")
    record = Universe(date=today, tickers_json=tickers[:500])
    session.add(record)
    session.commit()
    session.refresh(record)
    return record.tickers_json


def latest_universe(session) -> List[str]:
    record = session.query(Universe).order_by(Universe.created_at.desc()).first()
    return record.tickers_json if record else []
