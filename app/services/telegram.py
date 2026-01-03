import logging
from typing import Any, Dict

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _parse_response(response: httpx.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        data = response.text
    message_id = None
    ok_value = response.is_success
    if isinstance(data, dict):
        message_id = data.get("result", {}).get("message_id")
        ok_value = bool(data.get("ok", response.is_success))
    return {
        "ok": ok_value,
        "status_code": response.status_code,
        "response": data,
        "message_id": str(message_id) if message_id is not None else None,
    }


def send_message_with_http_response(text: str) -> Dict[str, Any]:
    """Send a message and return detailed Telegram response data."""

    settings = get_settings()
    if not settings.alerts_enabled:
        logger.info("Alerts disabled. Message would be: %s", text)
        return {
            "ok": False,
            "status_code": 0,
            "response": "alerts-disabled",
            "message_id": "alerts-disabled",
        }
    if not settings.telegram_enabled:
        logger.info("Telegram disabled. Message would be: %s", text)
        return {
            "ok": False,
            "status_code": 0,
            "response": "telegram-disabled",
            "message_id": "disabled",
        }

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": settings.telegram_chat_id, "text": text}

    with httpx.Client(timeout=10) as client:
        response = client.post(url, json=payload)

    return _parse_response(response)


def send_message(text: str) -> str:
    result = send_message_with_http_response(text)
    return result.get("message_id") or ""
