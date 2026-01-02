# AI Trader Alert Engine

Minimal FastAPI service that demonstrates the requested architecture: universe builder, setup detectors, scoring, options selector, governor, trade state machine, Telegram templates, and Render deployment notes.

## Quickstart

```bash
pip install fastapi uvicorn sqlalchemy pytest
uvicorn app.main:app --reload
```

## Render deployment
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Cron suggestions:
  - POST `/scan/scalp` every minute RTH
  - POST `/scan/day` every 5 minutes RTH
  - POST `/scan/swing` every 60 minutes RTH
  - POST `/state/update` every minute RTH
  - POST `/universe/rebuild` daily 08:45 ET

## Environment variables
See `app/config.py` for defaults. Key values: `MASSIVE_API_KEY`, `MASSIVE_BASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`, `ENABLE_RTH_ONLY`.

## Tests and fixtures
- Unit tests live in `app/tests/` and use fixtures under `app/tests/fixtures/`.
- Run with `pytest`.

## Example Telegram outputs
Templates under `app/services/templates.py` provide deterministic messages for TRADE IDEA, I'M IN, and I'M OUT alerts. Tests rely on the text formatting to assert flows.

## Database
SQLite for development (see `DATABASE_URL` default). Models live in `app/models.py`; production can swap `DATABASE_URL` for Postgres. Alembic placeholder is under `app/migrations/`.
