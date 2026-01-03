# AI Trader — Automated Market-Scanning Trade Alerts

Investor-ready engine that scans high-volume equities/ETFs, scores setups, and ships formatted trade alerts (stock + options) to Telegram.

## Executive Summary
- FastAPI service that scans liquid tickers, detects repeatable setups, and formats “ready-to-send” alerts.
- Built for operators who need credible, low-touch alerting; engineers can deploy/extend via a clean API surface.
- Differentiator: deterministic templates, explicit guardrails (RTH-only, cooldowns), and an auditable state machine for in/out updates.
- Markets: focuses on a configurable universe (seeded with major ETFs; designed to ingest top-volume equities up to ~500 names via the universe rebuild job).
- Delivery: Telegram today; Discord and multi-channel routing are on the roadmap.
- Core loop: rebuild universe → scan (day/scalp/swing) → score → alert → track state → send “I’m in/out” follow-ups.

## What It Produces (Sample Alerts)
Realistic examples using the live templates in `app/services/templates.py`.

**A) TRADE IDEA (Day)**
```text
🚨 TRADE IDEA — NVDA CALLS

I'm looking long NVDA here — Trend pullback into VWAP.

**How I'm playing it (CALLS):**
- **Contract:** NVDA240621C010000 | Exp 2024-06-21
- **Entry:** 118.50
- **Stop:** 116.40
- **Targets:** 121.00 → 124.50

Indicator snapshot: uptrend intact; 1.6x relative volume; reclaiming VWAP; RSI 58.
```

**B) I'M IN (entry triggered)**
```text
✅ I'M IN — NVDA CALLS

I'm in NVDA now — trigger hit at 118.60.

- **Stop stays:** 116.40
- **Next:** 121.00 first, then 124.50 if momentum holds.
```

**C) I'M OUT (exit/target)**
```text
🏁 I'M OUT — NVDA CALLS
Target hit.
```

> Options selection is supported today via the options selector; affordability/advanced contract curation improvements are marked as Planned in the roadmap.

## Product Features
### Scanning & Universe
- **Implemented:** Configurable universe builder with always-include tickers; daily rebuild endpoint (`POST /universe/rebuild`) persists the latest list.
- **Planned:** Automated ingestion of top 500 volume stocks + ETFs (Cron-driven rebuild).

### Strategy Engine (Signals)
- **Implemented:** Multiple detectors (`trend_pullback`, `breakout_volume`, `vwap_reclaim`, `mean_reversion_to_vwap`, `bollinger_squeeze`, `reversal_divergence`) scored via `app.services.scoring`.
- **Implemented:** Timeframe-specific scans via `POST /scan/day`, `/scan/scalp`, `/scan/swing` with scoring/filters before alerting.
- **Planned:** Additional strategies and adaptive scoring.

### Trade State Machine
- **Implemented:** Lifecycle of `watching → triggered (I'm in) → exited (I'm out)` with `/state/update` applying price checks and updating DB state.
- **Implemented:** Cooldown + one-open-trade-per-ticker guardrails in `app.services.governor`.

### Alerts & Delivery
- **Implemented:** Telegram integration with deterministic message templates for Trade Idea, I'M IN, and I'M OUT.
- **Planned:** Discord and channel-specific formatting.

### Data & Storage
- **Implemented:** SQLAlchemy models with Postgres/SQLite via `DATABASE_URL`; stores universes, signals, trades, and state transitions.

### Safety & Guardrails
- **Implemented:** Regular-trading-hours-only toggle (`ENABLE_RTH_ONLY`), per-ticker cooldowns, max alerts per ticker per day, and Telegram disable switch for dry runs.
- **Planned:** Per-ticker rate limiting beyond cooldowns and user-level permissions.
- **Always:** "No financial advice" disclaimer baked into ops guidance.

## Architecture (High-level)
```
[Market Data API] -> [Universe Builder] -> [Scanners] -> [Scoring] -> [Alert Composer] -> [Telegram]
                            |                    |                      |
                            v                    v                      v
                          [DB] <----------- [Trade State Machine] <- [State Update]
```

## How It Works (Plain English)
- Pull a configurable list of liquid tickers (ETFs always included; rebuildable daily).
- Fetch price/volume/indicator snapshots per ticker.
- Run setup detectors (pullbacks, breakouts, VWAP plays, squeezes, divergences).
- Score confidence and filter for the best candidate per scan run.
- Attempt an options contract pick when enabled; fall back to stock-only framing if contracts fail liquidity/price checks.
- Compose a Telegram-ready message (trade idea or stock-only) using deterministic templates.
- Persist a trade record and enforce cooldowns/one-open-rule per ticker.
- Continuously update trades via `/state/update` to announce "I'm in" triggers and "I'm out" exits.

## Deploy / Ops (Render-first)
**Operator Setup (Render Web Service)**
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**Environment Variables**
- `MASSIVE_API_KEY` / `MASSIVE_BASE_URL`: Market data access.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: Alert delivery; set `TELEGRAM_DISABLE=true` to mute.
- `DATABASE_URL`: Postgres/SQLite connection string.
- `ENABLE_RTH_ONLY`: Enforce regular-hours scans/state updates.
- `ENV`, `ALERTS_ENABLED`, scoring/option thresholds (see `app/config.py`) for tuning.

**Cron Jobs (call the web endpoints; do NOT start uvicorn in cron)**
- State updates every minute: `curl -X POST https://<service>.onrender.com/state/update`
- Day scans every 5 minutes: `curl -X POST https://<service>.onrender.com/scan/day`
- Universe rebuild daily: `curl -X POST https://<service>.onrender.com/universe/rebuild`

## API Endpoints (Quick Reference)
| Method | Path | Purpose |
| --- | --- | --- |
| GET | /health | Liveness check (returns `{ "status": "ok" }`). |
| POST | /scan/day | Run day-timeframe scan and push the top alert. |
| POST | /scan/scalp | Run scalp scan. |
| POST | /scan/swing | Run swing scan. |
| POST | /state/update | Advance trade states and send in/out alerts. |
| POST | /universe/rebuild | Recreate the ticker universe for future scans. |
| POST | /test/telegram | Send a test message to verify Telegram (available in code today). |

## Roadmap (Next 30/60/90 Days)
- Planned: Additional setup detectors and adaptive weighting by market regime.
- Planned: Improved options contract selection (affordability filters, spread-aware) and risk-sizing suggestions.
- Planned: Backtesting harness + alert performance dashboard.
- Planned: Discord delivery and per-channel formatting.
- Planned: Multi-user subscriptions and per-user preferences.
- Planned: Authentication token for cron-triggered calls.

## Compliance & Disclaimer
- Not financial advice; for educational and research purposes only.
- Trading involves risk; only trade what you can afford to lose.
- Past performance is not indicative of future results.
