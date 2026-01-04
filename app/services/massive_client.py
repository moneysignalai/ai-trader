import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.services.options_normalize import normalize_snapshot_response


logger = logging.getLogger(__name__)


class MassiveClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.massive_base_url
        self.api_key = api_key or settings.massive_api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        params.setdefault("apiKey", self.api_key)
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.request(method, path, params=params)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    logger.warning("Rate limited on %s %s; sleeping for %ss", method, path, retry_after)
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as exc:  # network issues
                logger.error("HTTP error for %s %s: %s", method, path, exc)
                if attempt >= self.max_retries:
                    raise
                time.sleep(2**attempt)
            except httpx.HTTPStatusError as exc:
                logger.error("Bad response %s for %s %s: %s", exc.response.status_code, method, path, exc)
                if 500 <= exc.response.status_code < 600 and attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise
        raise RuntimeError("Failed request")

    def get_aggregates(
        self,
        ticker: str,
        range: int = 1,
        timespan: str = "minute",
        limit: Optional[int] = None,
        frm: Optional[str] = None,
        to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if limit:
            params["limit"] = limit
        if frm:
            params["from"] = frm
        if to:
            params["to"] = to
        path = f"/v2/aggs/ticker/{ticker}/range/{range}/{timespan}/{frm or '2024-01-01'}/{to or '2024-12-31'}"
        data = self._request("GET", path, params=params)
        return data.get("results", []) if isinstance(data, dict) else []

    def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        data = self._request("GET", f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
        if not isinstance(data, dict):
            return {"last": None}
        last_trade = data.get("lastTrade", {}) or {}
        last_quote = data.get("lastQuote", {}) or {}
        price = last_trade.get("p") or last_quote.get("p") or last_quote.get("last" )
        return {
            "last_trade": last_trade,
            "last_quote": last_quote,
            "last": price,
        }

    def get_options_chain_snapshot(self, ticker: str) -> Dict[str, Any]:
        try:
            raw = self._request("GET", f"/v3/snapshot/options/{ticker}")
            normalized = normalize_snapshot_response(raw or {})
            return {"results": normalized}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Options snapshot unavailable for %s: %s", ticker, exc)
            return {"results": []}

    def get_top_volume(self, on_date: str) -> List[str]:
        data = self._request("GET", f"/v2/aggs/grouped/locale/us/market/stocks/{on_date}")
        results = data.get("results", []) if isinstance(data, dict) else []
        sorted_results = sorted(results, key=lambda r: r.get("v", 0), reverse=True)
        return [row.get("T") for row in sorted_results if row.get("T")]
