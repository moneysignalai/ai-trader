"""Database schema compatibility utilities for the trades table."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

LAST_MIGRATION_RESULT: dict[str, Any] | None = None


def _table_exists(conn, table_name: str) -> bool:
    dialect = getattr(conn.engine, "dialect", None)
    name = getattr(dialect, "name", "") if dialect else ""
    if name == "sqlite":
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        ).first()
        return result is not None

    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name LIMIT 1"
        ),
        {"name": table_name},
    ).first()
    return result is not None


def _existing_columns(conn, table_name: str) -> list[dict[str, str]]:
    dialect = getattr(conn.engine, "dialect", None)
    name = getattr(dialect, "name", "") if dialect else ""
    if name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info('{table_name}')")).mappings()
        return [{"name": row["name"], "type": row["type"]} for row in rows]

    rows = conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :name "
            "ORDER BY ordinal_position"
        ),
        {"name": table_name},
    ).mappings()
    return [{"name": row["column_name"], "type": row["data_type"]} for row in rows]


def _dialect_supported(conn) -> bool:
    dialect = getattr(conn.engine, "dialect", None)
    name = getattr(dialect, "name", "") if dialect else ""
    return name in {"postgresql", "postgres", "sqlite"}


def ensure_trades_schema(engine: Engine) -> dict[str, Any]:
    """Ensure the trades table has expected columns and backfills compatible values."""

    global LAST_MIGRATION_RESULT

    summary: dict[str, Any] = {
        "status": "ok",
        "table_exists": False,
        "added_columns": [],
        "backfilled": {},
    }

    try:
        with engine.begin() as conn:
            if not _table_exists(conn, "trades"):
                summary.update({"status": "skipped", "reason": "no trades table"})
                LAST_MIGRATION_RESULT = summary
                return summary

            if not _dialect_supported(conn):
                summary.update(
                    {"status": "skipped", "reason": "unsupported dialect", "table_exists": True}
                )
                LAST_MIGRATION_RESULT = summary
                return summary

            summary["table_exists"] = True
            existing_columns = _existing_columns(conn, "trades")
            existing_names = {col["name"] for col in existing_columns}

            dialect = getattr(conn.engine, "dialect", None)
            name = getattr(dialect, "name", "") if dialect else ""
            table_ref = "public.trades" if name in {"postgresql", "postgres"} else "trades"

            column_ddls = {
                "setup": "setup TEXT",
                "setup_name": "setup_name TEXT",
                "trade_uuid": "trade_uuid TEXT",
                "status": "status TEXT",
                "side": "side TEXT",
                "opened_at": "opened_at TIMESTAMPTZ",
                "closed_at": "closed_at TIMESTAMPTZ",
                "entry_price": "entry_price DOUBLE PRECISION",
                "entry_trigger_price": "entry_trigger_price DOUBLE PRECISION",
                "stop_price": "stop_price DOUBLE PRECISION",
                "target_prices": "target_prices JSONB",
                "last_price": "last_price DOUBLE PRECISION",
                "max_favorable": "max_favorable DOUBLE PRECISION",
                "exit_reason": "exit_reason TEXT",
                "alert_message_id": "alert_message_id TEXT",
                "last_alert_hash": "last_alert_hash TEXT",
                "option_symbol": "option_symbol TEXT",
                "entry_trigger": "entry_trigger TEXT",
                "t1": "t1 DOUBLE PRECISION",
                "t2": "t2 DOUBLE PRECISION",
                "timeframe": "timeframe TEXT",
            }

            for col_name, ddl in column_ddls.items():
                try:
                    if name in {"postgresql", "postgres"}:
                        conn.execute(text(f"ALTER TABLE {table_ref} ADD COLUMN IF NOT EXISTS {ddl}"))
                    elif col_name not in existing_names:
                        conn.execute(text(f"ALTER TABLE {table_ref} ADD COLUMN {ddl}"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Unable to add column %s: %s", col_name, exc)
                if col_name not in existing_names:
                    summary["added_columns"].append(col_name)

            if "trade_uuid" in column_ddls and name in {"postgresql", "postgres"}:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_trade_uuid "
                        "ON public.trades (trade_uuid)"
                    )
                )

            backfilled: dict[str, int] = {}

            if "setup" in column_ddls and "setup_name" in existing_names:
                result = conn.execute(
                    text(
                        f"UPDATE {table_ref} SET setup = setup_name "
                        "WHERE setup IS NULL AND setup_name IS NOT NULL"
                    )
                )
                backfilled["setup"] = result.rowcount or 0

            if "setup_name" in column_ddls:
                if "setup" in existing_names:
                    result = conn.execute(
                        text(
                            f"UPDATE {table_ref} SET setup_name = setup "
                            "WHERE setup_name IS NULL AND setup IS NOT NULL"
                        )
                    )
                    backfilled["setup_name_from_setup"] = result.rowcount or 0
                result = conn.execute(
                    text(
                        f"UPDATE {table_ref} SET setup_name = 'unknown' "
                        "WHERE setup_name IS NULL"
                    )
                )
                backfilled["setup_name_unknown"] = result.rowcount or 0

                try:
                    conn.execute(
                        text(f"ALTER TABLE {table_ref} ALTER COLUMN setup_name SET DEFAULT 'unknown'")
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Unable to set default for trades.setup_name: %s", exc)

            if "status" in column_ddls and "state" in existing_names:
                result = conn.execute(
                    text(
                        f"UPDATE {table_ref} SET status = state "
                        "WHERE status IS NULL AND state IS NOT NULL"
                    )
                )
                backfilled["status"] = result.rowcount or 0

            if "stop_price" in column_ddls and "stop" in existing_names:
                result = conn.execute(
                    text(
                        f"UPDATE {table_ref} SET stop_price = stop "
                        "WHERE stop_price IS NULL AND stop IS NOT NULL"
                    )
                )
                backfilled["stop_price"] = result.rowcount or 0

            if "entry_trigger" in existing_names and "entry_trigger_price" in column_ddls:
                result = conn.execute(
                    text(
                        f"UPDATE {table_ref} "
                        "SET entry_trigger_price = CAST(entry_trigger AS DOUBLE PRECISION) "
                        "WHERE entry_trigger_price IS NULL "
                        "AND CAST(entry_trigger AS TEXT) ~ '^[0-9]+(\\.[0-9]+)?$'"
                    )
                )
                backfilled["entry_trigger_price"] = result.rowcount or 0

            if "timeframe" in column_ddls:
                try:
                    conn.execute(text(f"ALTER TABLE {table_ref} ALTER COLUMN timeframe SET DEFAULT 'day'"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Unable to set default for trades.timeframe: %s", exc)

                try:
                    result = conn.execute(
                        text(f"UPDATE {table_ref} SET timeframe='day' WHERE timeframe IS NULL")
                    )
                    backfilled["timeframe"] = result.rowcount or 0
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Unable to backfill trades.timeframe: %s", exc)

                if name in {"postgresql", "postgres"}:
                    try:
                        conn.execute(text(f"ALTER TABLE {table_ref} ALTER COLUMN timeframe SET NOT NULL"))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Unable to enforce NOT NULL on trades.timeframe: %s", exc)

            summary["backfilled"] = backfilled
            logger.info(
                "Trades schema migration applied: added=%s backfilled=%s", summary["added_columns"], backfilled
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Trades schema migration failed: %s", exc)
        summary.update({"status": "error", "reason": str(exc)})

    LAST_MIGRATION_RESULT = summary
    return summary


def describe_trades_schema(engine: Engine) -> dict[str, Any]:
    """Return trades table existence and column metadata."""
    with engine.connect() as conn:
        dialect = getattr(conn.engine, "dialect", None)
        name = getattr(dialect, "name", "") if dialect else ""
        if name not in {"postgresql", "postgres", "sqlite"}:
            return {"table_exists": False, "columns": [], "reason": "unsupported dialect"}
        if not _table_exists(conn, "trades"):
            return {"table_exists": False, "columns": []}
        columns = _existing_columns(conn, "trades")
        return {"table_exists": True, "columns": columns}


def get_last_migration_result() -> dict[str, Any] | None:
    return LAST_MIGRATION_RESULT
