import re

from fastapi.testclient import TestClient

from app.main import app


def test_test_telegram_uses_mmddyyyy(monkeypatch):
    captured = {}

    def fake_send(message: str):
        captured["message"] = message
        return {"ok": True, "status_code": 200, "response": "ok"}

    monkeypatch.setattr("app.main.send_message_with_http_response", fake_send)

    client = TestClient(app)
    response = client.post("/test/telegram")

    assert response.status_code == 200
    assert "message" in captured
    assert re.search(r"Timestamp: \d{2}-\d{2}-\d{4} \d{2}:\d{2} [AP]M ET", captured["message"])
    assert re.search(r"\b\d{2}-\d{2}-\d{4}\b", captured["message"])
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}T", captured["message"])
    assert captured["message"].count("Timestamp:") == 1
