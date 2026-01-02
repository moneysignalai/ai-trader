from dataclasses import dataclass, field
from typing import Dict, List, Type


class DummyMeta:
    def __init__(self):
        self.tables: Dict[Type, List] = {}

    def create_all(self, bind=None):
        from app.db import SessionLocal  # local import to avoid cycle
        SessionLocal.storage = {model: [] for model in self.tables}

    def drop_all(self, bind=None):
        from app.db import SessionLocal
        SessionLocal.storage = {model: [] for model in self.tables}


class BaseModel:
    id: int


class DummyBase:
    metadata = DummyMeta()


Base = DummyBase()
engine = None


class Query:
    def __init__(self, session, model, data):
        self.session = session
        self.model = model
        self.data = list(data)

    def filter(self, func):
        self.data = [row for row in self.data if func(row)]
        return self

    def all(self):
        return list(self.data)

    def count(self):
        return len(self.data)

    def first(self):
        return self.data[0] if self.data else None

    def order_by(self, _):
        return self

    def fetchall(self):
        return self.data


class SessionLocal:
    storage: Dict[Type, List] = {}

    def __init__(self):
        # ensure storage per instance points to class storage
        self.storage = SessionLocal.storage

    def add(self, obj):
        model = type(obj)
        if model not in self.storage:
            self.storage[model] = []
        if getattr(obj, "id", None) is None:
            obj.id = len(self.storage[model]) + 1
        self.storage[model].append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        return obj

    def close(self):
        pass

    def query(self, model):
        data = self.storage.get(model, [])
        return Query(self, model, data)

    def execute(self, _):
        # simple support for debug endpoints
        return Query(self, None, [])


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
