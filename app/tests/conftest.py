import os
import sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.db import Base, SessionLocal


@pytest.fixture(scope="function")
def session_with_db():
    Base.metadata.drop_all()
    Base.metadata.create_all()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
