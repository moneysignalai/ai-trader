from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.dates import (
    ET,
    format_et_timestamp,
    format_mmddyyyy,
    normalize_any_date_to_mmddyyyy,
    parse_mmddyyyy,
)


def test_normalize_any_date_variants():
    assert normalize_any_date_to_mmddyyyy("2026-01-09") == "01-09-2026"
    assert normalize_any_date_to_mmddyyyy("09-01-2026") == "09-01-2026"
    assert normalize_any_date_to_mmddyyyy("01-09-2026") == "01-09-2026"


def test_parse_mmddyyyy_roundtrip():
    parsed = parse_mmddyyyy("01-09-2026")
    assert isinstance(parsed, date)
    assert parsed.month == 1 and parsed.day == 9 and parsed.year == 2026


def test_normalize_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_any_date_to_mmddyyyy("2026/01/09")


def test_format_et_timestamp_respects_timezone():
    dt = datetime(2026, 1, 4, 1, 10, tzinfo=timezone.utc)
    assert format_et_timestamp(dt) == "01-03-2026 08:10 PM ET"


def test_format_et_timestamp_handles_naive_datetime():
    dt = datetime(2026, 1, 4, 5, 52)
    assert format_et_timestamp(dt) == "01-04-2026 12:52 AM ET"


def test_format_et_timestamp_strips_seconds_and_microseconds():
    dt = datetime(2026, 1, 4, 5, 52, 30, 123456, tzinfo=timezone.utc)
    assert format_et_timestamp(dt) == "01-04-2026 12:52 AM ET"


def test_format_mmddyyyy_works_for_date_and_datetime():
    date_only = date(2026, 1, 4)
    dt = datetime(2026, 1, 4, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert format_mmddyyyy(date_only) == "01-04-2026"
    assert format_mmddyyyy(dt) == "01-04-2026"


def test_format_et_timestamp_defaults_to_et():
    stamp = format_et_timestamp()
    parsed = datetime.strptime(stamp.replace(" ET", ""), "%m-%d-%Y %I:%M %p")
    assert parsed.tzinfo is None  # strptime result is naive
    assert stamp.endswith(" ET")
    assert ZoneInfo("America/New_York") == ET
