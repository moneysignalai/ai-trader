from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_preflight_endpoint(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("ENABLE_RTH_ONLY", "false")
    monkeypatch.setenv("UNIVERSE_SIZE", "123")

    client = TestClient(app)
    response = client.get("/preflight")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["telegram_enabled"] is True
    assert payload["db_connected"] is True
    assert payload["enable_rth_only"] is False
    assert payload["universe_size"] == 123
    assert payload["service_time_utc"].endswith("Z")
