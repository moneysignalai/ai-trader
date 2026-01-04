from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.utils.dates import (
    format_mmddyyyy_time,
    normalize_any_date_to_mmddyyyy,
    parse_mmddyyyy,
)


def test_normalize_any_date_variants():
    assert normalize_any_date_to_mmddyyyy("2026-01-09") == "01-09-2026"
    assert normalize_any_date_to_mmddyyyy("09-01-2026") == "01-09-2026"
    assert normalize_any_date_to_mmddyyyy("01-09-2026") == "01-09-2026"


def test_parse_mmddyyyy_roundtrip():
    parsed = parse_mmddyyyy("01-09-2026")
    assert isinstance(parsed, date)
    assert parsed.month == 1 and parsed.day == 9 and parsed.year == 2026


def test_normalize_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_any_date_to_mmddyyyy("2026/01/09")


def test_format_mmddyyyy_time_respects_timezone():
    dt = datetime(2026, 1, 4, 5, 52, 24, 253824, tzinfo=ZoneInfo("UTC"))
    assert format_mmddyyyy_time(dt) == "01-04-2026 12:52 AM ET"


def test_format_mmddyyyy_time_accepts_dates():
    date_only = date(2026, 1, 4)
    assert format_mmddyyyy_time(date_only) == "01-04-2026 12:00 AM ET"
