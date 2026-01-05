from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings


settings = get_settings()

engine = create_engine(settings.database_url, echo=settings.db_echo, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def table_exists(conn, table_name: str) -> bool:
    try:
        dialect = getattr(conn.engine, "dialect", None)
        if getattr(dialect, "name", "") == "sqlite":
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": table_name},
            ).first()
            return result is not None

        result = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :name LIMIT 1"
            ),
            {"name": table_name},
        ).first()
        return result is not None
    except Exception:
        return False


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    with session_scope() as session:
        yield session
