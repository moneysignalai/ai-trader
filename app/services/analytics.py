import logging

logger = logging.getLogger(__name__)


def record_event(event: str, payload: dict):
    logger.info("analytics: %s - %s", event, payload)
