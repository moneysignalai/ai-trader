# AI Trader Alert Engine

Minimal FastAPI service that demonstrates the requested architecture: universe builder, setup detectors, scoring, options selector, governor, trade state machine, Telegram templates, and Render deployment notes.

## Quickstart

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Deploy to Render

Render-ready defaults are provided via `render.yaml`.

1. Push this repo to your own GitHub account.
2. Create a **Render Web Service** and connect the repository.
3. Use these commands:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Set environment variables:
   - `MASSIVE_API_KEY` — API key for market data provider.
   - `MASSIVE_BASE_URL` — Base URL for the Massive API.
   - `TELEGRAM_BOT_TOKEN` — Telegram bot token for alerts.
   - `TELEGRAM_CHAT_ID` — Chat ID that should receive alerts (group IDs are negative numbers).
   - `TELEGRAM_DISABLE` — Optional; set `true` to disable Telegram during testing.
   - `ALERTS_ENABLED` — Kill switch; set `false` to log alerts without sending.
   - `DATABASE_URL` — Optional Postgres connection string (defaults to local SQLite).
   - `ENABLE_RTH_ONLY` — Limit scans to regular trading hours; defaults to `true`.
   - `RTH_START` / `RTH_END` — Optional overrides for RTH window (HH:MM, America/New_York by default).
5. Deploy and verify:
   - Open `https://<service>/health` and confirm `{"status":"ok"}`.
   - Check Render logs for "Application startup complete".

### Cron job examples

Trigger these endpoints via Render cron jobs or external schedulers:

- `curl -X POST https://<service>/scan/day`
- `curl -X POST https://<service>/state/update`
- `curl -X POST https://<service>/universe/rebuild`

## Render deployment notes
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Cron suggestions:
  - POST `/scan/scalp` every minute RTH
  - POST `/scan/day` every 5 minutes RTH
  - POST `/scan/swing` every 60 minutes RTH
  - POST `/state/update` every minute RTH
  - POST `/universe/rebuild` daily 08:45 ET

## Environment variables
See `app/config.py` for defaults. Key values: `MASSIVE_API_KEY`, `MASSIVE_BASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`, `ENABLE_RTH_ONLY`, `ALERTS_ENABLED`.

## Tests and fixtures
- Unit tests live in `app/tests/` and use fixtures under `app/tests/fixtures/`.
- Run with `pytest`.

## Example Telegram outputs
Templates under `app/services/templates.py` provide deterministic messages for TRADE IDEA, I'M IN, and I'M OUT alerts. Tests rely on the text formatting to assert flows.

## Database
SQLite for development (see `DATABASE_URL` default). Models live in `app/models.py`; production can swap `DATABASE_URL` for Postgres. Alembic placeholder is under `app/migrations/`.
