"""
tests/parsers/test_type_coercion.py

Phase 1 / Task 8 (ADR-0001) — regression protection for the type-
coercion and date-parsing helpers actually used by the parsers and
loaders. Every assertion here targets CURRENT, CONFIRMED behavior
(read from the real source files this session) -- not a redesigned or
idealized version of it. Where two helpers behave differently for the
same input (e.g. comma handling), that difference is asserted
explicitly rather than "fixed" here; fixing it is out of Task 8's
scope and would be a separate, explicitly-approved change.

Known, deliberately-NOT-fixed gaps encoded as real behavior below:
  - No source in the repo has dedicated "trace" (\"T\") rainfall
    handling; \"T\" is indistinguishable from any other unparseable
    string and silently becomes None everywhere.
  - scripts/database/load_ndma.py's to_int/to_float treat \"1,234\" as
    unparseable (float() chokes on the comma) while
    scripts/database/load_pdma.py's to_int strips commas first.
  - validation/rules.py and validation/translator.py each define a
    function twice in the same file; only the second (later) def in
    each file is importable/reachable. Tests target only what's
    actually reachable.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ==========================================================
# scripts/database/load_pdma.py -- to_int, parse_date
# (cleanly importable: no import-time DB connection)
# ==========================================================

from scripts.database.load_pdma import to_int as pdma_to_int
from scripts.database.load_pdma import parse_date as pdma_parse_date


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234", 1234),          # comma stripped
        ("1234", 1234),
        (" 42 ", 42),             # whitespace stripped
        (None, None),
        ("", None),
        ("-", None),
        ("N/A", None),
        ("12.5", None),           # bare int() cannot parse a decimal string
    ],
)
def test_pdma_to_int(raw, expected):
    assert pdma_to_int(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("15 August 2025", date(2025, 8, 15)),
        ("15.08.2025", date(2025, 8, 15)),
        ("August 15, 2025", date(2025, 8, 15)),
        ("15 Aug 2025", date(2025, 8, 15)),
        (None, None),
        ("", None),
        ("not a date", None),
        ("2025-08-15", None),  # NOT supported by load_pdma.parse_date's format list
    ],
)
def test_pdma_parse_date(raw, expected):
    assert pdma_parse_date(raw) == expected


# ==========================================================
# scripts/database/load_pmd.py -- parse_timestamp
# (cleanly importable: no import-time DB connection)
# ==========================================================

from scripts.database.load_pmd import parse_timestamp as pmd_parse_timestamp


def test_pmd_parse_timestamp_valid_iso():
    result = pmd_parse_timestamp("2026-08-12T00:00:16.469671")
    assert result == datetime(2026, 8, 12, 0, 0, 16, 469671)


@pytest.mark.parametrize(
    "raw",
    [None, "", "not a timestamp", "15 August 2025"],  # not ISO format
)
def test_pmd_parse_timestamp_invalid(raw):
    assert pmd_parse_timestamp(raw) is None


# ==========================================================
# scripts/parsing/parse_gauge.py -- to_float, extract_report_datetime
# (the only dayfirst=True user in the repo)
# ==========================================================

from scripts.parsing.parse_gauge import to_float as gauge_to_float
from scripts.parsing.parse_gauge import extract_report_datetime


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234.5", 1234.5),   # comma stripped
        ("1234.5 ft", 1234.5),  # trailing unit text ignored via regex
        ("-3.2", -3.2),         # negative numbers supported (unlike other numeric helpers)
        (None, None),
        ("", None),
        ("-", None),
        ("N/A", None),
        ("T", None),  # no trace handling -- confirmed real current behavior
    ],
)
def test_gauge_to_float(raw, expected):
    assert gauge_to_float(raw) == expected


def test_gauge_extract_report_datetime_dayfirst():
    # Filename pattern: DD.MM.YYYY_HHMM -- confirms dayfirst=True is honored:
    # "01.07.2026_1800" must resolve to July 1st, not a nonsensical month 18.
    result = extract_report_datetime(Path("01.07.2026_1800Hrs.pdf"), "")
    assert result is not None
    parsed = datetime.fromisoformat(result)
    assert (parsed.month, parsed.day, parsed.year) == (7, 1, 2026)
    assert (parsed.hour, parsed.minute) == (18, 0)


def test_gauge_extract_report_datetime_no_match_returns_none():
    assert extract_report_datetime(Path("not_a_matching_name.pdf"), "no date here either") is None


# ==========================================================
# scripts/parsing/parse_rainfall.py -- parse_numeric
# NOTE: NOT None-safe by design (production only ever calls it with
# pre-cleaned strings) -- test asserts this real, non-defensive contract.
# ==========================================================

from scripts.parsing.parse_rainfall import parse_numeric


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("12.5", 12.5),
        ("8", 8.0),
        ("", None),
        ("N/A", None),
        ("-", None),
        ("T", None),  # no trace handling -- confirmed real current behavior
    ],
)
def test_rainfall_parse_numeric(raw, expected):
    assert parse_numeric(raw) == expected


def test_rainfall_parse_numeric_none_raises():
    # Documents the real, non-defensive contract: callers must
    # pre-clean values (production always does, via clean_text()).
    with pytest.raises(TypeError):
        parse_numeric(None)


# ==========================================================
# scripts/parsing/pmd/utils.py -- extract_number
# (the only cross-module numeric helper import found in the repo)
# ==========================================================

from scripts.parsing.pmd.utils import extract_number


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("38 °C", 38.0),
        ("48%", 48.0),
        (None, None),
        ("N/A", None),
        ("-", None),
    ],
)
def test_pmd_extract_number(raw, expected):
    assert extract_number(raw) == expected


# ==========================================================
# validation/rules.py -- valid_temperature, valid_humidity, valid_city
# valid_forecast (each defined twice in the file; only the LIVE,
# later definition is importable/reachable -- these tests confirm
# the live behavior, not the shadowed dead-code behavior)
# ==========================================================

from validation.rules import valid_temperature, valid_humidity, valid_city, valid_forecast


@pytest.mark.parametrize(
    "value, expected",
    [
        (-20, True),   # live range is -20..60, NOT the dead code's -10..60
        (60, True),
        (-21, False),
        (61, False),
        ("not a number", False),
    ],
)
def test_valid_temperature_live_range(value, expected):
    assert valid_temperature(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, True),
        (100, True),
        (-1, False),
        (101, False),
    ],
)
def test_valid_humidity(value, expected):
    assert valid_humidity(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Lahore", True),
        ("unknown", False),   # live def rejects this case-insensitively; dead def did not
        ("Unknown", False),
        ("UNKNOWN", False),
        ("", False),
        (None, False),
    ],
)
def test_valid_city_live_behavior(value, expected):
    assert valid_city(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Sunny with a chance of rain", True),
        ("", False),
        (None, False),
    ],
)
def test_valid_forecast(value, expected):
    assert valid_forecast(value) is expected


# ==========================================================
# validation/translator.py -- normalize_city
# (live def returns str and is NOT None-safe; the dead, shadowed def
# returned a dict and was None-safe -- test the live, reachable one)
# ==========================================================

from validation.translator import normalize_city


def test_normalize_city_known_urdu():
    # A known Urdu entry that maps to an English name
    assert normalize_city("لاہور") == "Lahore"


def test_normalize_city_unknown_passthrough():
    assert normalize_city("SomeCityNotInMap") == "SomeCityNotInMap"


def test_normalize_city_none_raises():
    # Documents the real, non-defensive contract of the live definition.
    with pytest.raises(AttributeError):
        normalize_city(None)


# ==========================================================
# scripts/database/load_ndma.py -- to_int, to_float, parse_date
#
# This module opens a live DB connection AT IMPORT TIME
# (`with engine.connect() as conn:` at module scope, not inside a
# function). To import it for testing without touching Postgres, we
# mock config.database's `engine` attribute to a no-op before first
# importing scripts.database.load_ndma. This is a pure test-side
# technique -- load_ndma.py itself is not modified.
# ==========================================================

def _import_load_ndma_with_mocked_engine():
    """
    Import scripts.database.load_ndma without touching a real database.

    load_ndma.py does `from config.database import engine` and then,
    at module scope, `with engine.connect() as conn: ...`. If
    `config.database` is imported first and its `engine` attribute is
    replaced with a mock BEFORE `scripts.database.load_ndma` is first
    imported, load_ndma's `from config.database import engine` binds
    to the mock and the module-level `with engine.connect()...` block
    runs against a no-op context manager instead of a real database.
    """

    if "scripts.database.load_ndma" in sys.modules:
        return sys.modules["scripts.database.load_ndma"]

    import config.database as db_config  # noqa: E402  (intentional lazy import)

    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = "mocked"

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    original_engine = db_config.engine
    db_config.engine = mock_engine

    try:
        import scripts.database.load_ndma as load_ndma_module  # noqa: E402
    finally:
        # Restore config.database.engine for any other module that
        # imports it fresh after this point (load_ndma.py itself has
        # already bound its own module-level `engine` name to the
        # mock by now, which is fine -- it is not used again after
        # the module-level connectivity check at import time).
        db_config.engine = original_engine

    return load_ndma_module


try:
    _load_ndma = _import_load_ndma_with_mocked_engine()
    _LOAD_NDMA_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - reported, not silently swallowed
    _load_ndma = None
    _LOAD_NDMA_IMPORT_ERROR = exc


@pytest.mark.skipif(
    _load_ndma is None,
    reason=f"scripts.database.load_ndma could not be imported even with a mocked "
    f"DB engine: {_LOAD_NDMA_IMPORT_ERROR!r}",
)
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234", None),   # comma NOT stripped -- float() raises -- differs from load_pdma.to_int
        ("1234", 1234),
        ("12.5", 12),      # int(float(...)) -- differs from load_pdma.to_int
        (None, None),
        ("", None),
        ("-", None),
        ("N/A", None),
    ],
)
def test_ndma_to_int(raw, expected):
    assert _load_ndma.to_int(raw) == expected


@pytest.mark.skipif(
    _load_ndma is None,
    reason=f"scripts.database.load_ndma could not be imported even with a mocked "
    f"DB engine: {_LOAD_NDMA_IMPORT_ERROR!r}",
)
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1234.5", 1234.5),
        ("1,234.5", None),  # comma NOT stripped -- float() raises
        (None, None),
        ("-", None),
        ("N/A", None),
    ],
)
def test_ndma_to_float(raw, expected):
    assert _load_ndma.to_float(raw) == expected


@pytest.mark.skipif(
    _load_ndma is None,
    reason=f"scripts.database.load_ndma could not be imported even with a mocked "
    f"DB engine: {_LOAD_NDMA_IMPORT_ERROR!r}",
)
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("15 August 2025", date(2025, 8, 15)),
        ("15 Aug 2025", date(2025, 8, 15)),
        ("2025-08-15", date(2025, 8, 15)),  # ISO IS supported here, unlike load_pdma.parse_date
        (None, None),
        ("", None),
        ("15.08.2025", None),  # NOT supported by load_ndma.parse_date's format list
    ],
)
def test_ndma_parse_date(raw, expected):
    assert _load_ndma.parse_date(raw) == expected


# ==========================================================
# Cross-loader documentation tests: the confirmed, real behavioral
# differences between load_ndma.to_int and load_pdma.to_int, encoded
# as executable assertions so a future "fix" to either one is a
# visible, deliberate decision rather than a silent drift.
# ==========================================================

@pytest.mark.skipif(
    _load_ndma is None,
    reason=f"scripts.database.load_ndma could not be imported even with a mocked "
    f"DB engine: {_LOAD_NDMA_IMPORT_ERROR!r}",
)
def test_comma_handling_differs_between_ndma_and_pdma_to_int():
    assert _load_ndma.to_int("1,234") is None
    assert pdma_to_int("1,234") == 1234


@pytest.mark.skipif(
    _load_ndma is None,
    reason=f"scripts.database.load_ndma could not be imported even with a mocked "
    f"DB engine: {_LOAD_NDMA_IMPORT_ERROR!r}",
)
def test_decimal_string_handling_differs_between_ndma_and_pdma_to_int():
    assert _load_ndma.to_int("12.5") == 12
    assert pdma_to_int("12.5") is None
