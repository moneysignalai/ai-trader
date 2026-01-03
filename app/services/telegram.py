import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


def send_message(text: str) -> str:
    settings = get_settings()
    if not settings.alerts_enabled:
        logger.info("Alerts disabled. Message would be: %s", text)
        return "alerts-disabled"
    if settings.telegram_disable:
        logger.info("Telegram disabled. Message would be: %s", text)
        return "disabled"
    # In production, use httpx to send. For now, log and return placeholder id.
    logger.info("Sending telegram message: %s", text)
    return "mocked-message-id"
