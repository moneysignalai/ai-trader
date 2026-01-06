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

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        log_errors: bool = True,
    ) -> Any:
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
                if log_errors:
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

    def _log_snapshot_failure(
        self,
        method_name: str,
        path: str,
        exc: Exception,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        status = None
        snippet = None
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            status = exc.response.status_code
            try:
                snippet = (exc.response.text or "")[:200]
            except Exception:  # noqa: BLE001
                snippet = None
        elif isinstance(exc, httpx.RequestError) and hasattr(exc, "response"):
            response = getattr(exc, "response", None)
            if response is not None:
                status = getattr(response, "status_code", None)
                try:
                    snippet = (getattr(response, "text", "") or "")[:200]
                except Exception:  # noqa: BLE001
                    snippet = None

        payload = {"path": path, "status": status, "snippet": snippet}
        if extra:
            payload.update(extra)

        logger.warning(
            "Snapshot call failed method=%s path=%s status=%s err=%s snippet=%s",
            method_name,
            path,
            status,
            exc,
            snippet,
            exc_info=True,
            extra=payload,
        )

    def get_aggregates(
        self,
        ticker: str,
        range: int = 1,
        timespan: str = "minute",
        limit: Optional[int] = None,
        frm: Optional[str] = None,
        to: Optional[str] = None,
        sort: Optional[str] = None,
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
        if sort:
            params["sort"] = sort
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

    def latest_price_from_aggregates(self, ticker: str) -> Optional[float]:
        today_et = et_today_date()
        frm = iso_yyyy_mm_dd(today_et - timedelta(days=7))
        to = iso_yyyy_mm_dd(today_et)

        try:
            candles = self.get_aggregates(
                ticker=ticker,
                range=1,
                timespan="minute",
                frm=frm,
                to=to,
                limit=1,
                sort="desc",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Latest price from aggregates failed",
                extra={"ticker": ticker, "error": str(exc), "from": frm, "to": to},
            )
            return None

        if not candles:
            logger.info(
                "Latest price from aggregates empty",
                extra={"ticker": ticker, "from": frm, "to": to},
            )
            return None

        latest = candles[0]
        close = None
        if isinstance(latest, dict):
            close = latest.get("c") or latest.get("close") or latest.get("o") or latest.get("h") or latest.get("l")

        if close is None:
            logger.info(
                "Latest price from aggregates missing close",
                extra={"ticker": ticker, "from": frm, "to": to, "keys": list(latest.keys()) if isinstance(latest, dict) else None},
            )
            return None

        try:
            return float(close)
        except (TypeError, ValueError):  # noqa: PERF203
            logger.info(
                "Latest price from aggregates close not numeric",
                extra={"ticker": ticker, "close": close},
            )
            return None

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

    def get_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Return a normalized stock snapshot dict with a stable `last` field.

        This project originally targeted Polygon-style snapshot responses, but many
        deployments point MASSIVE_BASE_URL to Massive (api.massive.com), which uses
        a different snapshot surface (ex: `/v3/snapshot` unified snapshot).
        """
        # 0) Massive stock snapshot endpoint (preferred for api.massive.com stock snapshots)
        try:
            massive_price = self.massive_stock_snapshot_price(ticker)
            if massive_price is not None:
                return {"last": massive_price, "last_trade": {}, "last_quote": {}}
        except Exception as exc:  # noqa: BLE001
            self._log_snapshot_failure(
                method_name="massive_stock_snapshot_price",
                path=f"/v3/snapshot/stocks/{ticker}",
                exc=exc,
            )

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
        except Exception as exc:  # noqa: BLE001
            self._log_snapshot_failure(
                method_name="get_snapshot_polygon",
                path=f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                exc=exc,
            )

        # 2) Massive unified snapshot (preferred for api.massive.com)
        match = self.unified_snapshot_single_ticker(ticker, type="stocks")

        if not isinstance(match, dict):
            return None

        last_trade = match.get("last_trade") or {}
        last_quote = match.get("last_quote") or {}
        session = match.get("session") or {}
        price = (
            (last_trade.get("price") or last_trade.get("p"))
            or (last_quote.get("price") or last_quote.get("p"))
            or (session.get("last") or session.get("close") or session.get("c"))
        )

        return {"last_trade": last_trade, "last_quote": last_quote, "last": price, "raw": match}

    def massive_stock_snapshot_price(self, ticker: str) -> Optional[float]:
        snap = self.unified_snapshot_single_ticker(ticker, type="stocks")
        if not snap:
            return None

        try:
            return self.unified_snapshot_price(snap)
        except Exception:  # noqa: BLE001
            return None

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

    def unified_snapshot_single_ticker(self, ticker: str, type: str = "stocks") -> Optional[Dict[str, Any]]:  # noqa: A002
        try:
            data = self._request(
                "GET",
                "/v3/snapshot",
                # Unified snapshot lexicographic search uses `ticker`, but we want an exact match
                params={"ticker": ticker, "type": type, "limit": 1},
                log_errors=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._log_snapshot_failure(
                method_name="unified_snapshot_single_ticker",
                path="/v3/snapshot",
                exc=exc,
                extra={"ticker": ticker, "type": type},
            )
            return None

        payload: Dict[str, Any] = data if isinstance(data, dict) else {}
        results = payload.get("results")
        request_id = payload.get("request_id")

        if not isinstance(results, list) or not results:
            logger.warning(
                "Unified snapshot missing results",
                extra={"ticker": ticker, "type": type, "request_id": request_id},
            )
            return None

        match = next(
            (row for row in results if row.get("ticker") == ticker and row.get("type") == type),
            results[0] if isinstance(results[0], dict) else None,
        )

        if not isinstance(match, dict):
            logger.warning(
                "Unified snapshot no match",
                extra={"ticker": ticker, "type": type, "request_id": request_id},
            )
            return None

        if "error" in match or "message" in match:
            logger.warning(
                "Unified snapshot returned error",
                extra={
                    "ticker": ticker,
                    "type": type,
                    "request_id": request_id,
                    "error": match.get("error") or match.get("message"),
                },
            )
            return None

        logger.info(
            "Unified snapshot ok",
            extra={
                "ticker": ticker,
                "type": type,
                "market_status": match.get("market_status"),
                "price": match.get("last") or match.get("last_price") or match.get("price"),
            },
        )

        return match

    def unified_snapshot_price(self, snapshot: Dict[str, Any]) -> Optional[float]:
        if not isinstance(snapshot, dict):
            return None

        last_trade = snapshot.get("last_trade") or {}
        last_quote = snapshot.get("last_quote") or {}
        session = snapshot.get("session") or {}
        price = (
            (last_trade.get("price") or last_trade.get("p"))
            or (last_quote.get("price") or last_quote.get("p"))
            or (session.get("last") or session.get("close") or session.get("c"))
            or snapshot.get("last")
            or snapshot.get("last_price")
            or snapshot.get("price")
        )

        try:
            return float(price)
        except (TypeError, ValueError):  # noqa: PERF203
            return None

    def last_close_from_aggregates(
        self,
        ticker: str,
        lookback_days: int = 5,
        timespan: str = "minute",
        multiplier: int = 1,
    ) -> Optional[float]:
        end_date = et_today_date()
        start_date = end_date - timedelta(days=lookback_days)
        frm = iso_yyyy_mm_dd(start_date)
        to = iso_yyyy_mm_dd(end_date)

        try:
            candles = self.get_aggregates(
                ticker=ticker,
                range=multiplier,
                timespan=timespan,
                frm=frm,
                to=to,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Aggregates fallback failed", extra={"ticker": ticker, "error": str(exc), "from": frm, "to": to}
            )
            return None

        if not candles:
            logger.info(
                "Aggregates fallback empty",
                extra={"ticker": ticker, "from": frm, "to": to, "timespan": timespan, "multiplier": multiplier},
            )
            return None

        last_candle = candles[-1]
        close = None
        if isinstance(last_candle, dict):
            close = last_candle.get("close") or last_candle.get("c")

        if close is None:
            logger.info(
                "Aggregates fallback missing close",
                extra={"ticker": ticker, "from": frm, "to": to, "keys": list(last_candle.keys()) if isinstance(last_candle, dict) else None},
            )
            return None

        logger.info(
            "Aggregates fallback price computed",
            extra={"ticker": ticker, "price": close, "from": frm, "to": to, "timespan": timespan, "multiplier": multiplier},
        )
        try:
            return float(close)
        except (TypeError, ValueError):  # noqa: PERF203
            logger.info(
                "Aggregates fallback close not numeric",
                extra={"ticker": ticker, "close": close, "from": frm, "to": to},
            )
            return None
