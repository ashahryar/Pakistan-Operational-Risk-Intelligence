"""
tests/source_inventory/test_historical_coverage.py

Phase 1 / Task 14 (ADR-0001) -- deterministic validation tests for
docs/source_inventory/historical_coverage.csv. No live DB, no
internet -- reads the checked-in CSV file directly, stdlib `csv` only.
"""

from __future__ import annotations

import csv
import re

from tests.source_inventory.conftest import PROJECT_ROOT

HISTORICAL_CSV = PROJECT_ROOT / "docs" / "source_inventory" / "historical_coverage.csv"

REQUIRED_FIELDS = [
    "source_organization", "dataset_or_material", "hazard_family", "classification",
    "earliest_verified", "latest_verified", "historical_depth", "current_or_live",
    "geography", "geographic_granularity", "format", "access_method", "official_url",
    "estimated_file_count", "estimated_record_count", "estimated_storage", "freshness",
    "priority", "acquisition_tier", "pori_use", "verification_status", "notes",
]

VALID_PRIORITIES = {"P0", "P1", "P2", "P3", "P4"}
VALID_TIERS = {"Tier 1", "Tier 2", "Tier 3", "Do Not Acquire Automatically"}
VALID_VERIFICATION_STATUSES = {"VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED"}

# A bare 4-digit year, or ISO YYYY-MM / YYYY-MM-DD, or the honest-unknown
# placeholder -- anything else is not a valid "verified date" value.
_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
UNKNOWN = "Unknown / Requires verification"


def _read_rows():
    with open(HISTORICAL_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _year_of(value: str) -> int | None:
    if value == UNKNOWN or not value.strip():
        return None
    m = re.match(r"^(\d{4})", value.strip())
    return int(m.group(1)) if m else None


def test_csv_file_exists_and_parses():
    assert HISTORICAL_CSV.exists(), f"{HISTORICAL_CSV} does not exist"
    rows = _read_rows()
    assert len(rows) > 0


def test_header_has_every_required_column_in_order():
    with open(HISTORICAL_CSV, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert header == REQUIRED_FIELDS


def test_every_row_has_all_required_fields_non_null():
    rows = _read_rows()
    for row in rows:
        assert set(row.keys()) == set(REQUIRED_FIELDS), row
        for field in REQUIRED_FIELDS:
            assert row[field] is not None, f"{row.get('dataset_or_material')} missing {field}"
            assert row[field] != "", (
                f"{row['dataset_or_material']}.{field} is blank -- use "
                f"'{UNKNOWN}' instead of an empty cell"
            )


def test_no_duplicate_dataset_records():
    rows = _read_rows()
    seen = set()
    for row in rows:
        key = (row["source_organization"], row["dataset_or_material"])
        assert key not in seen, f"duplicate record: {key}"
        seen.add(key)


def test_priority_values_are_from_the_defined_scale():
    rows = _read_rows()
    for row in rows:
        assert row["priority"] in VALID_PRIORITIES, row["priority"]


def test_acquisition_tier_values_are_from_the_defined_set():
    rows = _read_rows()
    for row in rows:
        assert row["acquisition_tier"] in VALID_TIERS, row["acquisition_tier"]


def test_verification_status_values_are_from_the_defined_set():
    rows = _read_rows()
    for row in rows:
        assert row["verification_status"] in VALID_VERIFICATION_STATUSES, row["verification_status"]


def test_verified_records_have_a_real_official_url():
    """
    A record marked VERIFIED must be backed by a real URL -- otherwise
    the verification claim is unsubstantiated. PARTIALLY_VERIFIED/
    UNVERIFIED records may legitimately have an Unknown URL (e.g. the
    Federal-Flood-Commission-named-but-unvisited Irrigation Departments
    row).
    """
    rows = _read_rows()
    for row in rows:
        if row["verification_status"] == "VERIFIED":
            url = row["official_url"].strip()
            assert url != UNKNOWN, f"{row['dataset_or_material']} is VERIFIED but has no URL"
            assert "http" in url, f"{row['dataset_or_material']}: official_url doesn't look like a URL: {url!r}"


def test_unverified_records_do_not_claim_a_verified_date_range():
    """
    An UNVERIFIED record must not simultaneously claim a specific
    earliest/latest date -- that would be a contradiction between the
    verification_status column and the date columns.
    """
    rows = _read_rows()
    for row in rows:
        if row["verification_status"] == "UNVERIFIED":
            assert row["earliest_verified"] == UNKNOWN, (
                f"{row['dataset_or_material']} is UNVERIFIED but claims "
                f"earliest_verified={row['earliest_verified']!r}"
            )
            assert row["latest_verified"] == UNKNOWN, (
                f"{row['dataset_or_material']} is UNVERIFIED but claims "
                f"latest_verified={row['latest_verified']!r}"
            )


def test_date_fields_are_valid_dates_or_the_unknown_placeholder():
    rows = _read_rows()
    for row in rows:
        for field in ("earliest_verified", "latest_verified"):
            value = row[field]
            assert value == UNKNOWN or _DATE_RE.match(value), (
                f"{row['dataset_or_material']}.{field} is not a valid "
                f"YYYY / YYYY-MM / YYYY-MM-DD value or {UNKNOWN!r}: {value!r}"
            )


def test_no_contradictory_historical_ranges():
    """
    Where both earliest_verified and latest_verified are real dates,
    earliest must not be after latest.
    """
    rows = _read_rows()
    for row in rows:
        early = _year_of(row["earliest_verified"])
        late = _year_of(row["latest_verified"])
        if early is not None and late is not None:
            assert early <= late, (
                f"{row['dataset_or_material']}: earliest_verified "
                f"({row['earliest_verified']}) is after latest_verified "
                f"({row['latest_verified']})"
            )


def test_no_negative_volume_estimates():
    """
    Any numeric-looking figure inside the estimate fields must not be
    negative. Fields are free text (ranges/estimates are allowed and
    expected), so this only rejects an explicit negative number, not
    ranges or qualitative text.
    """
    # A genuine negative number: a '-' immediately followed by a digit,
    # with no digit and no other '-' immediately before it (so "1-5" and
    # "2024-2026" ranges, and free-text '--' dashes, are not flagged).
    negative_re = re.compile(r"(?<![\d-])-\d")
    rows = _read_rows()
    for row in rows:
        for field in ("estimated_file_count", "estimated_record_count", "estimated_storage"):
            value = row[field]
            assert not negative_re.search(value), (
                f"{row['dataset_or_material']}.{field} looks like a "
                f"negative estimate: {value!r}"
            )


def test_at_least_one_p0_tier1_verified_record_exists():
    """
    The acquisition plan's Tier 1 list must be backed by at least one
    real VERIFIED, P0, Tier 1 record -- otherwise Tier 1 would be an
    aspirational label with no verified evidence behind it.
    """
    rows = _read_rows()
    assert any(
        row["priority"] == "P0" and row["acquisition_tier"] == "Tier 1"
        and row["verification_status"] == "VERIFIED"
        for row in rows
    )
