import logging
import re
from datetime import date, timedelta
from typing import Dict, List

from app.config import get_settings
from app.models import Universe
from app.services.massive_client import MassiveClient


logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"^FILL\d+$")


def is_placeholder_ticker(ticker: str) -> bool:
    return bool(_PLACEHOLDER_RE.match(ticker or ""))


def contains_placeholder_tickers(tickers: List[str]) -> bool:
    return any(is_placeholder_ticker(ticker) for ticker in tickers)


def _fetch_reference_tickers(client: MassiveClient) -> List[str]:
    return client.get_reference_tickers()


def _volume_by_ticker(client: MassiveClient, target_date: date) -> Dict[str, float]:
    records = client.get_grouped_aggregates(target_date.isoformat())
    volumes: Dict[str, float] = {}
    for row in records:
        ticker = row.get("T")
        volume = row.get("v")
        if ticker and volume is not None:
            volumes[ticker] = float(volume)
    return volumes


def build_universe(session, *, client: MassiveClient | None = None, target_date: date | None = None) -> List[str]:
    settings = get_settings()
    client = client or MassiveClient()
    target_date = target_date or date.today()

    volumes = _volume_by_ticker(client, target_date)
    if not volumes:
        logger.warning("No grouped aggregates for %s, trying previous day", target_date)
        fallback_date = target_date - timedelta(days=1)
        volumes = _volume_by_ticker(client, fallback_date)
        target_date = fallback_date

    if not volumes:
        raise ValueError("Unable to build universe: no volume data available")

    reference = set(_fetch_reference_tickers(client))
    if not reference:
        raise ValueError("Unable to build universe: no reference tickers found")

    exclude = set(settings.exclude_tickers)
    base = []
    for ticker in settings.always_include_tickers:
        if ticker and ticker not in exclude:
            base.append(ticker)

    sorted_by_volume = sorted(
        ((ticker, volume) for ticker, volume in volumes.items() if ticker in reference and ticker not in exclude),
        key=lambda pair: pair[1],
        reverse=True,
    )

    top_ranked = [ticker for ticker, _ in sorted_by_volume[:500]]
    tickers = list(dict.fromkeys(base + top_ranked))

    limit = max(settings.universe_size, len(base))
    tickers = tickers[:limit]

    record = Universe(date=target_date, tickers_json=tickers)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record.tickers_json


def latest_universe(session) -> List[str]:
    record = session.query(Universe).order_by(Universe.created_at.desc()).first()
    return record.tickers_json if record else []
