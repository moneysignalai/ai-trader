from sqlalchemy import create_engine

from app.services.db_migrate import ensure_trades_schema


def test_ensure_trades_schema_handles_missing_table():
    engine = create_engine("sqlite:///:memory:")

    result = ensure_trades_schema(engine)

    assert isinstance(result, dict)
    assert result.get("status") == "skipped"
    assert result.get("reason") == "no trades table"
