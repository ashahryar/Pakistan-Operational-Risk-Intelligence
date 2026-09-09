"""
tests/parsers/test_pmd_golden.py

Phase 1 / Task 8 (ADR-0001) -- golden-file regression tests for the
three PMD parser functions:

  - scripts/parsing/pmd/daily_parser.py::parse_daily_forecast()
  - scripts/parsing/pmd/weekly_parser.py::parse_weekly_outlook()
  - scripts/parsing/pmd/alerts_parser.py::parse_weather_alert()

REPORTED COVERAGE CONSTRAINT (not a shortcut -- the underlying raw
data genuinely doesn't exist in more than one copy): unlike NDMA/PDMA,
PMD has always overwritten `latest.json` in place at both the raw and
parsed layers (the project's documented, not-yet-fixed archival gap).
Exactly ONE real historical snapshot exists per domain today. So:

  - daily_forecast / weekly_outlook: 1 real happy-path fixture (the
    actual current latest.json) + 1 derived negative-path fixture
    each (see tests/fixtures/pmd/*_derived.json and their
    "_derived_note" field -- a real row from the actual raw file plus
    one deliberately-injected too-short row, never presented as
    additional real data).
  - weather_alerts: 1 real happy-path fixture only.
    alerts_parser.py has no per-record rejection path at all
    (confirmed: no write_quarantine import/call anywhere in that
    file) -- there is no negative path to test here.

Isolation: write_quarantine is monkeypatched to an in-memory spy for
every test in this file (including the happy-path ones, defensively,
in case a future data change introduces an unexpected rejection) --
this suite never writes to the real dq.quarantine table. RAW_FILE is
only monkeypatched for the two derived-fixture tests; the happy-path
tests read the real, tracked data/raw/pmd/.../latest.json files
as-is (read-only) and never write anywhere (parse_daily_forecast/
parse_weekly_outlook/parse_weather_alert only build and return a
dict -- saving to data/parsed/ is a separate function this suite
never calls).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.parsing.pmd.daily_parser as daily_parser
import scripts.parsing.pmd.weekly_parser as weekly_parser
import scripts.parsing.pmd.alerts_parser as alerts_parser

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pmd"
EXPECTED_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "expected" / "pmd"

VOLATILE_FIELDS: set[str] = set()  # scraped_at is sourced from the raw file, not wall-clock -- stable


def _spy_quarantine(monkeypatch, module):
    calls = []

    def fake_write_quarantine(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(module, "write_quarantine", fake_write_quarantine)
    return calls


def _strip_volatile(records):
    if isinstance(records, list):
        return [{k: v for k, v in r.items() if k not in VOLATILE_FIELDS} for r in records]
    return {k: v for k, v in records.items() if k not in VOLATILE_FIELDS}


# ==========================================================
# DAILY FORECAST
# ==========================================================

def test_pmd_daily_forecast_golden_happy_path(monkeypatch):
    calls = _spy_quarantine(monkeypatch, daily_parser)

    parsed, processed, rejected = daily_parser.parse_daily_forecast()

    assert processed > 0
    assert rejected == 0, "the real, current daily_forecast latest.json is expected to have zero rejections"
    assert len(parsed) == processed
    assert calls == []

    expected_path = EXPECTED_DIR / "daily_forecast.json"
    assert expected_path.exists(), f"missing golden fixture: {expected_path}"
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert _strip_volatile(parsed) == _strip_volatile(expected)


def test_pmd_daily_forecast_negative_path_row_too_short(monkeypatch):
    calls = _spy_quarantine(monkeypatch, daily_parser)

    derived_file = FIXTURES_DIR / "daily_forecast_derived.json"
    assert derived_file.exists(), f"missing derived fixture: {derived_file}"
    monkeypatch.setattr(daily_parser, "RAW_FILE", derived_file)

    parsed, processed, rejected = daily_parser.parse_daily_forecast()

    assert processed == 2
    assert rejected == 1
    assert len(parsed) == 1
    assert parsed[0]["city"] == "Islamabad"  # normalize_city passthrough for the real, valid row

    assert len(calls) == 1
    assert calls[0]["source"] == "pmd"
    assert calls[0]["domain"] == "daily_forecast"
    assert calls[0]["reason_code"] == "row_too_short"


# ==========================================================
# WEEKLY OUTLOOK
# ==========================================================

def test_pmd_weekly_outlook_golden_happy_path(monkeypatch):
    calls = _spy_quarantine(monkeypatch, weekly_parser)

    parsed, processed, rejected = weekly_parser.parse_weekly_outlook()

    assert processed > 0
    assert rejected == 0, "the real, current weekly_outlook latest.json is expected to have zero rejections"
    assert len(parsed) == processed
    assert calls == []

    expected_path = EXPECTED_DIR / "weekly_outlook.json"
    assert expected_path.exists(), f"missing golden fixture: {expected_path}"
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert _strip_volatile(parsed) == _strip_volatile(expected)


def test_pmd_weekly_outlook_negative_path_row_too_short(monkeypatch):
    calls = _spy_quarantine(monkeypatch, weekly_parser)

    derived_file = FIXTURES_DIR / "weekly_outlook_derived.json"
    assert derived_file.exists(), f"missing derived fixture: {derived_file}"
    monkeypatch.setattr(weekly_parser, "RAW_FILE", derived_file)

    parsed, processed, rejected = weekly_parser.parse_weekly_outlook()

    assert processed == 2
    assert rejected == 1
    assert len(parsed) == 1

    assert len(calls) == 1
    assert calls[0]["source"] == "pmd"
    assert calls[0]["domain"] == "weekly_outlook"
    assert calls[0]["reason_code"] == "row_too_short"


# ==========================================================
# WEATHER ALERTS -- happy path only (no rejection path exists)
# ==========================================================

def test_pmd_weather_alerts_golden_happy_path():
    result = alerts_parser.parse_weather_alert()

    assert isinstance(result, dict)
    assert result["category"] == "weather_alerts"

    expected_path = EXPECTED_DIR / "weather_alerts.json"
    assert expected_path.exists(), f"missing golden fixture: {expected_path}"
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert _strip_volatile(result) == _strip_volatile(expected)


def test_pmd_alerts_parser_has_no_quarantine_path():
    """
    Documents a real, confirmed gap rather than assuming otherwise: if
    a rejection path is ever added to alerts_parser.py, this test
    should be revisited (and a negative-path fixture added) rather
    than silently continuing to skip it.
    """
    import inspect

    source = inspect.getsource(alerts_parser)
    assert "write_quarantine" not in source
