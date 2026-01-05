from sqlalchemy import create_engine, text

from app.services.db_migrate import ensure_trades_schema


def test_ensure_trades_schema_handles_missing_table():
    engine = create_engine("sqlite:///:memory:")

    result = ensure_trades_schema(engine)

    assert isinstance(result, dict)
    assert result.get("status") == "skipped"
    assert result.get("reason") == "no trades table"


def test_db_auto_migrate_backfills_setup_name_from_setup():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE trades (id INTEGER PRIMARY KEY, ticker TEXT, setup TEXT)"))
        conn.execute(
            text("INSERT INTO trades (ticker, setup) VALUES (:ticker, :setup)"),
            [{"ticker": "AAPL", "setup": "pb"}, {"ticker": "MSFT", "setup": None}],
        )

    result = ensure_trades_schema(engine)
    assert result.get("status") == "ok"

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT setup, setup_name FROM trades ORDER BY id")).mappings().all()

    assert rows[0]["setup_name"] == "pb"
    assert rows[1]["setup_name"] == "unknown"
