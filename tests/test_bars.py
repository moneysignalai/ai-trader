from app.services.bars import normalize_bar


def test_normalize_short_keys():
    bar = {"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100}

    normalized = normalize_bar(bar)

    assert normalized == {
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": 1.5,
        "volume": 100,
    }


def test_normalize_full_keys_passthrough():
    bar = {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}

    normalized = normalize_bar(bar)

    assert normalized == bar
