# AI Trader — Market Intelligence & Trade Alerts

AI Trader is an AI-first intelligence engine that scouts liquid markets, scores setups like a confident discretionary trader, and publishes trade-ready alerts. Delivery is channel-agnostic: Telegram is just one distribution path alongside Discord, webhooks, or dashboards.

## Overview
- Curates a universe of high-volume stocks and ETFs for clean execution.
- Evaluates bullish and bearish setups with context-aware scoring and confirmation logic.
- Chooses between options and stock-only framing based on liquidity, cost, and clarity of risk.
- Publishes lifecycle alerts: Trade Idea, I'M IN, and I'M OUT.
- Keeps risk defined with explicit entries, stops, targets, and trade states.

## System Architecture (Map)
```
Market Data (Massive/Polygon)
        |
        v
Universe Builder (Top Volume)
        |
        v
Signal Engine (Setups + Scoring + Filters)
        |
        v
Instrument Selector (Stock vs Options)
        |
        v
Trade Lifecycle (watching -> in -> out) stored in DB
        |
        v
Distribution (Telegram/Discord/Webhook)
```

## Intelligence Flow
The engine behaves like a disciplined trader: it starts with a liquid watchlist, gathers current context, and only advances ideas when multiple factors agree. Signals are filtered for confirmation and risk definition before choosing whether to express the trade via options or stock. Each alert carries the reasoning, pricing quality, and a clear status (waiting for trigger vs trigger hit), so operators can act with conviction.

## What the system does
- Scans top-volume stocks and ETFs for high-conviction trade ideas.
- Generates CALL and PUT option plans when contracts are liquid and fairly priced.
- Falls back to stock-only framing when options fail affordability or liquidity checks.
- Defines entry, stop, and target levels for every idea and tracks lifecycle events.
- Publishes alerts to interchangeable channels (Telegram, Discord, webhook, etc.).

## Example Alerts (Medium Style)
Trade Idea (Options)
```
🚨 TRADE IDEA — NVDA CALLS
Confidence score: 88
Entry 118.50 | Stop 116.40 | Targets 121.00 → 124.50
Contract: Exp 2024-06-21 | Strike 100.00 | Type CALL | DTE 5
Pricing: Mid 2.45 | Bid 2.35 / Ask 2.55 | Spread 8.16%
Greeks/IV: Delta 0.55 | IV 45.00%
Liquidity: Volume 12500 | OI 68420
Reasons:
- Pullback to VWAP with buyers defending
- Trend intact with high-volume reclaim
- Semis leading market strength
Waiting for trigger
```

Trade Idea (Stock Only)
```
🚨 TRADE IDEA — AMD STOCK
Confidence score: 82
Entry 154.20 | Stop 150.80 | Targets 158.00 → 162.50
Reasons:
- Bullish breakout with expanding volume
- Holding above intraday support
Plan: respect the stop, trim at first target, trail toward the second target.
Waiting for trigger
```

I'M IN
```
✅ I'M IN — AMD CALLS
Trigger hit at 154.30 (plan 154.20).
Risk map: Stop 150.80 | Targets 158.00 → 162.50
Plan: trim at first target, let a runner aim for the second with stop discipline.
```

I'M OUT
```
🏁 I'M OUT — AMD CALLS
Target hit.
Entry 154.20 | Exit 158.00 | Stop 150.80 | Targets 158.00 → 162.50 P/L≈3.80 (2.46%)
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

Telegram (one of several output channels):
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
