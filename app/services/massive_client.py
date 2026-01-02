import json
from pathlib import Path
from typing import Any, Dict, List


class MassiveClient:
    def __init__(self, base_path: str | None = None):
        self.base_path = Path(base_path) if base_path else None

    def _load_fixture(self, name: str) -> Dict[str, Any]:
        if not self.base_path:
            raise RuntimeError("Fixture path not configured")
        with open(self.base_path / name) as f:
            return json.load(f)

    def get_aggregates(self, ticker: str, *_args, **_kwargs) -> List[Dict[str, Any]]:
        # for tests we just load fixture matching ticker if present
        try:
            return self._load_fixture(f"{ticker}_aggregates.json")
        except FileNotFoundError:
            return []

    def get_options_chain_snapshot(self, ticker: str) -> Dict[str, Any]:
        return self._load_fixture("sample_chain_snapshot.json")

    def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        try:
            data = self._load_fixture("sample_quotes.json")
            return data.get(ticker, {"last": None})
        except FileNotFoundError:
            return {"last": None}
