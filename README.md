# AI Trader — Telegram Alert Service

## Overview
AI-driven alert system that scans high-volume stocks and ETFs, evaluates bullish and bearish setups, and sends disciplined trade ideas to Telegram. It behaves like a professional trader sharing entries, stops, and targets with followers. Alerts can include option contracts or stock-only plans when options are too expensive.

## What the system does
- Scans top-volume stocks and ETFs for trade ideas.
- Generates CALL and PUT option ideas when contracts are liquid and affordable.
- Falls back to stock-only framing when options fail affordability or liquidity checks.
- Defines entry, stop, and target levels for each idea.
- Sends lifecycle alerts: Trade Idea, I'M IN, and I'M OUT.

## System Architecture & Intelligence Flow
The platform is organized as an intelligence engine that behaves like a disciplined trader. It ingests curated market context, scores opportunities with probabilistic and confirmation-based logic, decides how to express risk, and then publishes evolving trade states. Delivery is decoupled from intelligence; messaging is interchangeable.

### Market Data Layer
- Continuously evaluates a curated universe of high-volume equities and ETFs instead of scanning the entire market blindly.
- Pulls market context on-demand from external data sources, keeping the engine stateless between scans.
- Universe size is configurable and optimized for liquidity so that only actionable symbols enter the pipeline.

### Intelligence & Signal Layer
- Assesses bullish and bearish conditions using multiple factors together (trend, structure, volume, momentum) rather than single triggers.
- Scores and filters signals probabilistically; weak, conflicting, or low-conviction setups are discarded to prioritize quality over frequency.
- Uses context-aware and confirmation-based logic to require alignment across factors before advancing an idea.
- Maintains risk-defined framing by pairing every potential entry with precomputed stops and targets.

### Decision & Instrument Selection Layer
- Once a valid setup is confirmed, the system decides how to express it: options when liquidity and cost make sense, or stock-only when they do not.
- Evaluates option chain liquidity, pricing efficiency, and risk clarity; overpriced or thin contracts trigger an intentional fallback to shares.
- Emphasizes clarity of risk and execution practicality over forcing an options idea.

### Trade State & Lifecycle Layer
- Treats each trade idea as an evolving entity with clear states: watching, in, and out.
- Defines entries, stops, and targets up front and monitors how price behaves relative to those guardrails over time.
- State transitions drive updates—alerts signal movement from watching to in to out as conditions are met or invalidated.

### Distribution Layer
- Publishes state changes to external channels; Telegram is just one interchangeable endpoint alongside alternatives like Discord or web dashboards.
- Messaging remains decoupled so the intelligence engine is the durable core product.

### Execution Flow (Narrative)
1. Market context for the curated universe is evaluated to establish a real-time view of liquidity and structure.
2. A high-quality, context-aware setup is identified with probabilistic scoring across trend, volume, and momentum.
3. Risk parameters—entry, stop, and targets—are defined before any alert leaves the engine.
4. Instrument choice is made by testing options liquidity and cost; if inefficient, the plan defaults to stock-only.
5. A trade idea is published with its initial state as "watching."
6. Price action evolves, and the system tracks how it conforms to or violates the plan.
7. State changes (entering, hitting targets, stopping out, or invalidation) trigger follow-up alerts through the distribution layer.

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
