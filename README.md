# AI Trader Alert Engine

Minimal FastAPI service that demonstrates the requested architecture: universe builder, setup detectors, scoring, options selector, governor, trade state machine, Telegram templates, and Render deployment notes.

## Quickstart

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Deploy to Render

Make the service deployable with a copy/paste flow on Render:

1. Create a **Render Web Service** from this repo.
2. Use these settings (also shown in `render.yaml`):
   - Environment: **Python**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Configure environment variables:
   - `MASSIVE_API_KEY`
   - `MASSIVE_BASE_URL`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ENABLE_RTH_ONLY` (recommended: `true`)
   - `DATABASE_URL` (optional; defaults to local SQLite when unset)
4. Deploy and verify:
   - Open `https://<your-service>.onrender.com/health` and confirm `{ "status": "ok" }`.
   - Check logs for "Application startup complete".

### Cron job examples

Schedule these with Render Cron Jobs or an external scheduler:

- `curl -X POST https://<your-service>.onrender.com/universe/rebuild`
- `curl -X POST https://<your-service>.onrender.com/scan/day`
- `curl -X POST https://<your-service>.onrender.com/state/update`

## Environment variables
See `app/config.py` for defaults. Key values: `MASSIVE_API_KEY`, `MASSIVE_BASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`, `ENABLE_RTH_ONLY`, `ALERTS_ENABLED`.

## Tests and fixtures
- Unit tests live in `app/tests/` and use fixtures under `app/tests/fixtures/`.
- Run with `pytest`.

## Example Telegram outputs
Templates under `app/services/templates.py` provide deterministic messages for TRADE IDEA, I'M IN, and I'M OUT alerts. Tests rely on the text formatting to assert flows.

## Database
SQLite for development (see `DATABASE_URL` default). Models live in `app/models.py`; production can swap `DATABASE_URL` for Postgres. Alembic placeholder is under `app/migrations/`.
