# AI Trader — Telegram Alert Service

## Overview
AI-driven alert system that scans high-volume stocks and ETFs, evaluates bullish and bearish setups, and sends disciplined trade ideas to Telegram. It behaves like a professional trader sharing entries, stops, and targets with followers. Alerts can include option contracts or stock-only plans when options are too expensive.

## What the system does
- Scans top-volume stocks and ETFs for trade ideas.
- Generates CALL and PUT option ideas when contracts are liquid and affordable.
- Falls back to stock-only framing when options fail affordability or liquidity checks.
- Defines entry, stop, and target levels for each idea.
- Sends lifecycle alerts: Trade Idea, I'M IN, and I'M OUT.

## System Architecture (Technical Overview)
The service is deployed as a stateless FastAPI web app on Render. It exposes HTTP endpoints that are triggered by Render Cron Jobs; there is no always-on worker loop, so execution is event-driven. Market data is pulled on-demand from the Massive API, candidates are evaluated in-memory per scan, and trade state (entries, open positions, exits) is persisted in Postgres. Telegram is used only as a delivery channel—no orders are executed.

Execution flow:
1. Cron job triggers `/scan/day`.
2. Service fetches the universe of top-volume tickers.
3. Signals are evaluated for bullish and bearish setups.
4. Options are checked for affordability and liquidity.
5. A Trade Idea alert is formatted and sent to Telegram.
6. The trade is stored in the database as "watching".
7. Cron job triggers `/state/update`.
8. Open trades are checked against entry, stop, and targets.
9. I'M IN or I'M OUT alerts are sent.
10. Trade state is updated in the database.

Configuration notes:
- `ENABLE_RTH_ONLY` gates scans and state updates to regular trading hours.
- `ALERT_STYLE` controls alert verbosity without code changes (defaults to `medium`).
- `TELEGRAM_ENABLED` gates delivery; when false, messages are logged as "telegram-disabled".

## Example Alerts (Medium Style)
Trade Idea (Options)
```
🚨 TRADE IDEA — NVDA CALLS
Entry: 118.50 | Stop: 116.40 | Targets: 121.00 → 124.50
Contract: NVDA240621C010000 (CALL)
Why:
- Trend pullback into VWAP
- Uptrend intact; 1.6x volume; reclaiming VWAP
```

Trade Idea (Stock Only)
```
🚨 TRADE IDEA — AMD STOCK
Entry: 154.20 | Stop: 150.80 | Targets: 158.00 → 162.50
Options skipped: premiums above limit; playing shares only
Why:
- Bullish breakout with expanding volume
- Holding above intraday support
```

I'M IN
```
✅ I'M IN — AMD STOCK
Triggered at 154.30
Stop: 150.80 | Targets: 158.00 → 162.50
```

I'M OUT
```
🏁 I'M OUT — AMD STOCK
Target hit at 158.00
Recorded and removed from active watchlist
```

## Alert styles
`ALERT_STYLE` controls message verbosity only and does not require code changes:
- `short`
- `medium` (default)
- `deep`

If the value is unset or invalid, the system defaults to `medium`.

## Environment variables
Required:
- `DATABASE_URL`: Postgres connection string.
- `MASSIVE_API_KEY`: Massive API key for market data.
- `MASSIVE_BASE_URL`: Massive API base URL.

Telegram:
- `TELEGRAM_ENABLED`: Enable Telegram delivery when true; false disables sending but logs attempts as "telegram-disabled".
- `TELEGRAM_BOT_TOKEN`: Bot token used to send messages.
- `TELEGRAM_CHAT_ID`: Chat to receive alerts.

Trading / behavior:
- `UNIVERSE_SIZE`: Number of tickers to scan (default 20; recommended 500 for breadth).
- `ENABLE_RTH_ONLY`: Restrict scans and updates to regular trading hours when true.
- `ALERT_STYLE`: Alert verbosity (`short`, `medium`, `deep`).

## Endpoints
- `GET /health` — Liveness and DB connectivity check.
- `GET /preflight` — Returns key configuration flags and DB connectivity status.
- `POST /scan/day` — Runs the day scan and pushes the top alert candidate.
- `POST /state/update` — Advances trade states and sends I'M IN or I'M OUT alerts.
- `POST /universe/rebuild` — Rebuilds the ticker universe for future scans.
- `POST /test/telegram` — Sends a test message to verify Telegram delivery.

## Cron jobs (Render)
The service is designed to be triggered by Render Cron Jobs calling HTTP endpoints.
- Universe rebuild: daily call to `/universe/rebuild`.
- Scan: every few minutes during RTH call to `/scan/day`.
- State update: every few minutes during RTH call to `/state/update`.

## Testing
Example checks for operators:
- Test Telegram: `curl -X POST https://<service>.onrender.com/test/telegram`
- Preflight check: `curl https://<service>.onrender.com/preflight`
- Rebuild universe: `curl -X POST https://<service>.onrender.com/universe/rebuild`

## Deployment (Render)
- Runtime: `python-3.11.9`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --access-log`

## Disclaimer
Educational and informational use only. This system does not provide financial advice or execute trades.
