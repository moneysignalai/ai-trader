import importlib

import app.config as config


def _reload_config():
    importlib.reload(config)
    config.get_settings.cache_clear()


def test_min_signal_score_accepts_float(monkeypatch):
    monkeypatch.setenv("MIN_SIGNAL_SCORE", "6.0")
    _reload_config()

    settings = config.get_settings()

    assert settings.min_signal_score == 6.0

    monkeypatch.delenv("MIN_SIGNAL_SCORE", raising=False)
    _reload_config()


def test_min_signal_score_falls_back_to_min_score_day(monkeypatch):
    monkeypatch.delenv("MIN_SIGNAL_SCORE", raising=False)
    monkeypatch.setenv("MIN_SCORE_DAY", "82.5")
    _reload_config()

    settings = config.get_settings()

    assert settings.min_signal_score == 82.5

    monkeypatch.delenv("MIN_SCORE_DAY", raising=False)
    _reload_config()
