from datetime import date

import pytest

from app.utils.dates import normalize_any_date_to_mmddyyyy, parse_mmddyyyy


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
