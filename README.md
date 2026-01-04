# AI Trader — Market Intelligence & Trade Alerts

AI Trader is an AI-first intelligence engine that scouts liquid markets, scores setups like a confident discretionary trader, and publishes trade-ready alerts. Delivery is channel-agnostic: Telegram is just one distribution path alongside Discord, webhooks, or dashboards.

## Overview
- Curates a universe of high-volume stocks and ETFs for clean execution.
- Evaluates bullish and bearish setups with context-aware scoring and confirmation logic.
- Chooses between options and stock-only framing based on liquidity, cost, and clarity of risk.
- Publishes lifecycle alerts: Trade Idea, I'M IN, and I'M OUT.
- Keeps risk defined with explicit entries, stops, targets, and trade states.

## System Architecture & Intelligence Flow
```
Market Data (Massive)
        ↓
Universe Builder (Liquidity + Volume)
        ↓
Signal Intelligence Engine (Context + Scoring)
        ↓
Instrument Selection (Options vs Stock)
        ↓
Trade Lifecycle Manager (Watching → In → Out)
        ↓
Distribution Channels (Telegram, Discord, Webhook)
```

- **Market Data (Massive):** Streams option and equity snapshots as the factual base for every decision.
- **Universe Builder:** Filters to liquid, high-volume names so downstream signals have tight spreads and depth.
- **Signal Intelligence Engine:** Scores setups with contextual features (trend, momentum, structure) to mirror a confident discretionary trader.
- **Instrument Selection:** Chooses between options and stock based on liquidity, spreads, moneyness, and quality of fills.
- **Trade Lifecycle Manager:** Manages state transitions from watching → I'M IN → I'M OUT while keeping stops and targets explicit.
- **Distribution Channels:** Delivers finished intelligence to Telegram, Discord, or webhooks. Delivery is modular; the core product is the decision engine.

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

Underlying: NVDA @ 118.50
Contract: 06-21-2024 100.00C (DTE: 5)
Premium: 2.45 mid (2.35 x 2.55) | Spread: 8.2%
Vol/OI: 12500 / 68420
Delta: 0.55 | IV: 45.0%

Entry: 118.50
Stop: 116.40
Targets: 121.00 → 124.50

Why I like it:
• Pullback to VWAP with buyers defending
• Trend intact with high-volume reclaim
• Semis leading market strength

Waiting for trigger.
 
Timestamp: 06-14-2024 09:30 AM ET
```

Trade Idea (Stock Only)
```
🚨 TRADE IDEA — AMD (STOCK)

Entry: 154.20
Stop: 150.80
Targets: 158.00 → 162.50

Why stock over options:
• Options premiums elevated or illiquid
• Cleaner risk with shares

Plan is simple: respect the stop.
 
Timestamp: 06-14-2024 09:32 AM ET
```

I'M IN
```
✅ I'M IN — AMD CALLS

Entry filled: 154.30
Stop: 150.80
Targets: 158.00 → 162.50

Staying with the plan.
 
Timestamp: 06-14-2024 09:45 AM ET
```

I'M OUT
```
🏁 I'M OUT — AMD

Entry: 154.20
Exit: 158.00
Result: 2.5%

Trade closed. Risk managed.
 
Timestamp: 06-14-2024 11:15 AM ET
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
- Option selection guardrails (configurable): `OPT_MAX_MONEYNESS_PCT` (0.12), `OPT_MAX_SPREAD_PCT` (0.20), `OPT_MIN_DTE` (5), `OPT_MAX_DTE` (21), `OPT_MIN_VOLUME` (50), `OPT_MIN_OI` (200), `OPT_CALL_DELTA_MIN` (0.20), `OPT_CALL_DELTA_MAX` (0.55), `OPT_PUT_DELTA_MIN` (-0.55), `OPT_PUT_DELTA_MAX` (-0.20).

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
