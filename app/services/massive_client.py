import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlsplit

import httpx

from app.config import get_settings
from app.services.options_normalize import normalize_snapshot_response
from app.utils.dates import et_today_date, iso_yyyy_mm_dd
from app.utils.logging_utils import redact_url


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
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout, headers=self.headers)

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        safe_path = redact_url(f"{self.base_url}{path}")
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.request(method, path, params=params)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    logger.warning(
                        "Rate limited on %s %s; sleeping for %ss",
                        method,
                        safe_path,
                        retry_after,
                    )
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as exc:  # network issues
                logger.error("HTTP error for %s %s: %s", method, safe_path, redact_url(str(exc)))
                if attempt >= self.max_retries:
                    raise
                time.sleep(2**attempt)
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Bad response %s for %s %s: %s",
                    exc.response.status_code,
                    method,
                    safe_path,
                    redact_url(str(exc)),
                )
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

        if frm is None or to is None:
            today_et = et_today_date()
            default_from = iso_yyyy_mm_dd(today_et - timedelta(days=7))
            default_to = iso_yyyy_mm_dd(today_et)
            frm = frm or default_from
            to = to or default_to

        if timespan == "minute" and limit is None:
            limit = 5000

        if limit:
            params["limit"] = limit
        if frm:
            params["from"] = frm
        if to:
            params["to"] = to

        path = f"/v2/aggs/ticker/{ticker}/range/{range}/{timespan}/{frm}/{to}"
        data = self._request("GET", path, params=params)
        results = data.get("results", []) if isinstance(data, dict) else []
        logger.info(
            "Aggregates window ticker=%s from=%s to=%s candles=%s", ticker, frm, to, len(results)
        )
        return results

    def get_grouped_aggregates(self, on_date: str) -> List[Dict[str, Any]]:
        path = f"/v2/aggs/grouped/locale/us/market/stocks/{on_date}"
        data = self._request("GET", path)
        return data.get("results", []) if isinstance(data, dict) else []

    def get_reference_tickers(self, market: str = "stocks", locale: str = "us") -> List[str]:
        tickers: List[str] = []
        path: Optional[str] = "/v3/reference/tickers"
        params: Optional[Dict[str, Any]] = {
            "market": market,
            "active": "true",
            "limit": 1000,
            "locale": locale,
        }

        while path:
            data = self._request("GET", path, params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            for row in results:
                ticker = row.get("ticker")
                if ticker:
                    tickers.append(ticker)

            next_url = data.get("next_url") if isinstance(data, dict) else None
            if next_url:
                parsed = urlsplit(next_url)
                path = parsed.path
                params = {key: value for key, value in parse_qsl(parsed.query)}
            else:
                path = None
                params = None

        return tickers

    def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        """
        Return a normalized stock snapshot dict with a stable `last` field.

        This project originally targeted Polygon-style snapshot responses, but many
        deployments point MASSIVE_BASE_URL to Massive (api.massive.com), which uses
        a different snapshot surface (ex: `/v3/snapshot` unified snapshot).
        """
        # 1) Polygon-style snapshot (legacy compatibility)
        try:
            data = self._request(
                "GET",
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
            )
            if isinstance(data, dict):
                last_trade = data.get("lastTrade", {}) or {}
                last_quote = data.get("lastQuote", {}) or {}
                price = last_trade.get("p") or last_quote.get("p") or last_quote.get("last")
                if price is not None:
                    return {"last_trade": last_trade, "last_quote": last_quote, "last": price}
        except Exception:
            pass

        # 2) Massive unified snapshot (preferred for api.massive.com)
        try:
            data = self._request(
                "GET",
                "/v3/snapshot",
                params={"ticker": ticker, "type": "stocks"},
            )
            results = (data or {}).get("results") if isinstance(data, dict) else None
            first = (results[0] if isinstance(results, list) and results else {}) or {}

            last_trade = first.get("last_trade") or {}
            last_quote = first.get("last_quote") or {}
            session = first.get("session") or {}

            price = (
                (last_trade.get("price") or last_trade.get("p"))
                or (last_quote.get("price") or last_quote.get("p"))
                or (session.get("last") or session.get("close") or session.get("c"))
            )
            return {"last_trade": last_trade, "last_quote": last_quote, "last": price, "raw": first}
        except Exception:
            return {"last": None}

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
