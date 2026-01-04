from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo


_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MM_DD_YYYY_PATTERN = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])-(\d{4})$")
_DD_MM_YYYY_PATTERN = re.compile(r"^(0[1-9]|[12]\d|3[01])-(0[1-9]|1[0-2])-(\d{4})$")


def to_mmddyyyy_from_iso(iso_yyyy_mm_dd: str) -> str:
    dt = datetime.fromisoformat(str(iso_yyyy_mm_dd)).date()
    return dt.strftime("%m-%d-%Y")


def normalize_any_date_to_mmddyyyy(date_str: str) -> str:
    text = str(date_str)
    if _ISO_PATTERN.match(text):
        return to_mmddyyyy_from_iso(text)

    ddmm_match = _DD_MM_YYYY_PATTERN.match(text)
    mmdd_match = _MM_DD_YYYY_PATTERN.match(text)

    if ddmm_match and mmdd_match:
        first = int(text.split("-", 1)[0])
        second = int(text.split("-", 2)[1])
        if first > second:
            day, month, year = ddmm_match.group(1), ddmm_match.group(2), ddmm_match.group(3)
            return f"{month}-{day}-{year}"
        return text

    if ddmm_match:
        day, month, year = ddmm_match.group(1), ddmm_match.group(2), ddmm_match.group(3)
        return f"{month}-{day}-{year}"
    if mmdd_match:
        return text
    raise ValueError(f"Unrecognized date format: {date_str}")


def parse_mmddyyyy(date_str: str) -> date:
    normalized = normalize_any_date_to_mmddyyyy(date_str)
    return datetime.strptime(normalized, "%m-%d-%Y").date()


def format_mmddyyyy(dt_value: date | datetime) -> str:
    if isinstance(dt_value, datetime):
        dt_value = dt_value.date()
    return dt_value.strftime("%m-%d-%Y")


def format_mmddyyyy_time(dt_value: date | datetime, tz: str = "America/New_York") -> str:
    if isinstance(dt_value, date) and not isinstance(dt_value, datetime):
        dt_value = datetime.combine(dt_value, datetime.min.time())
    if not isinstance(dt_value, datetime):
        raise TypeError("dt_value must be a date or datetime instance")

    zone = ZoneInfo(tz)
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=zone)
    else:
        dt_value = dt_value.astimezone(zone)

    return dt_value.strftime("%m-%d-%Y %I:%M %p ET")

