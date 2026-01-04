from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def format_mmddyyyy(d: date | datetime) -> str:
    """
    Returns MM-DD-YYYY
    """
    if isinstance(d, datetime):
        d = d.astimezone(ET).date()
    return d.strftime("%m-%d-%Y")


def format_et_timestamp(dt: datetime | None = None) -> str:
    """
    Returns: MM-DD-YYYY HH:MM AM/PM ET
    Example: 01-04-2026 12:52 AM ET
    """
    if dt is None:
        dt = datetime.now(ET)
    else:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET)
        else:
            dt = dt.astimezone(ET)

    return dt.strftime("%m-%d-%Y %I:%M %p") + " ET"


def normalize_any_date_to_mmddyyyy(date_str: str) -> str:
    """
    Accepts:
    - YYYY-MM-DD (upstream ISO)
    - DD-MM-YYYY (legacy)
    - MM-DD-YYYY (canonical)
    Returns MM-DD-YYYY
    """
    if "-" not in date_str:
        raise ValueError("Invalid date")

    parts = date_str.split("-")

    # ISO
    if len(parts[0]) == 4:
        y, m, d = parts
        return f"{m}-{d}-{y}"

    # MM-DD-YYYY (already canonical)
    if int(parts[0]) <= 12:
        return date_str

    # DD-MM-YYYY (legacy)
    d, m, y = parts
    return f"{m}-{d}-{y}"


def parse_mmddyyyy(date_str: str) -> date:
    normalized = normalize_any_date_to_mmddyyyy(date_str)
    return datetime.strptime(normalized, "%m-%d-%Y").date()
