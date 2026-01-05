import json
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


def _truncate(value: Any, limit: int = 500) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "..."
    return value


def safe_log_extra(extra: Dict[Any, Any] | None) -> Dict[str, Any]:
    """Ensure logging extras are JSON-safe primitives.

    - Coerces keys to strings.
    - Serializes dicts/lists/sets/tuples to compact JSON strings.
    - Falls back to ``str(value)`` for any unsupported type.
    """

    if not extra:
        return {}

    safe: Dict[str, Any] = {}
    for key, value in extra.items():
        key_str = str(key)
        if isinstance(value, (dict, list, tuple, set)):
            try:
                safe_value: Any = json.dumps(value, default=str, separators=(",", ":"))
            except TypeError:
                safe_value = str(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe_value = value
        else:
            safe_value = str(value)
        safe[key_str] = safe_value

    return safe


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


def send_message(text: str) -> Dict[str, Any]:
    """Send a message and return the full Telegram response."""

    return send_message_with_http_response(text)


def send_message_id_only(text: str) -> str:
    """Send a message and return only the Telegram message id (if available)."""

    result = send_message_with_http_response(text)
    return result.get("message_id") or ""


def send_or_log(text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message and log failures with context."""

    context = context or {}
    logger.info("Sending Telegram alert", extra=safe_log_extra(context))
    result = send_message_with_http_response(text)
    if not result.get("ok"):
        logger.error(
            "Telegram send failed",  # static message for easier filtering
            extra=safe_log_extra(
                {
                    **context,
                    "telegram_status_code": result.get("status_code"),
                    "telegram_response": _truncate(result.get("response")),
                }
            ),
        )
    else:
        logger.info(
            "Telegram send ok message_id=%s", result.get("message_id"),
            extra=safe_log_extra(
                {
                    **context,
                    "telegram_status_code": result.get("status_code"),
                    "telegram_response": _truncate(result.get("response")),
                    "telegram_message_id": result.get("message_id"),
                }
            ),
        )
    return result
