from __future__ import annotations

import os
import re
from typing import Iterable


def redact_url(url: str, secrets: Iterable[str] | None = None) -> str:
    """Redact sensitive tokens from URLs before logging.

    The Massive API key can show up in legacy query strings; this helper replaces any
    provided secret with "***" to avoid leaking credentials in logs.
    """

    secrets_to_scrub = list(secrets or [])
    env_secret = os.getenv("MASSIVE_API_KEY")
    if env_secret:
        secrets_to_scrub.append(env_secret)

    redacted = url
    for secret in secrets_to_scrub:
        if not secret:
            continue
        escaped = re.escape(secret)
        redacted = re.sub(escaped, "***", redacted)
    return redacted

