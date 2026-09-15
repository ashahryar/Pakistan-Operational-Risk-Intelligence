"""
tests/source_inventory/test_source_inventory.py

Phase 1 / Task 13 (ADR-0001) -- deterministic validation tests for
docs/source_inventory/source_inventory.csv. No live DB, no internet --
reads the checked-in CSV file directly, using only the stdlib `csv`
module (no new dependency).
"""

from __future__ import annotations

import csv

from tests.source_inventory.conftest import INVENTORY_CSV

REQUIRED_FIELDS = [
    "record_type", "source_organization", "dataset_or_material", "official_url",
    "section_page", "data_type", "geography", "geographic_granularity",
    "frequency", "format", "extraction_method", "first_year_visible",
    "latest_year_visible", "historical_depth", "historical_classification",
    "current_or_live", "estimated_volume", "priority", "pori_use", "notes",
]

VALID_PRIORITIES = {"P0", "P1", "P2", "P3", "P4"}
VALID_CLASSIFICATIONS = {
    "LIVE_CURRENT", "RECENT_OPERATIONAL_HISTORY", "EVENT_HISTORY",
    "STATIC_REFERENCE", "Unknown / Requires verification",
}
VALID_RECORD_TYPES = {"primary_source", "supporting_source"}

PRIMARY_ORGS_REQUIRED = {
    "NDMA", "PDMA Punjab", "PDMA Sindh", "PDMA KP", "PDMA Balochistan", "PMD",
}


def _read_rows():
    with open(INVENTORY_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_csv_file_exists_and_parses():
    assert INVENTORY_CSV.exists(), f"{INVENTORY_CSV} does not exist"
    rows = _read_rows()
    assert len(rows) > 0, "inventory CSV parsed to zero rows"


def test_header_has_every_required_column_in_order():
    with open(INVENTORY_CSV, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert header == REQUIRED_FIELDS


def test_every_row_has_all_required_fields_non_null():
    rows = _read_rows()
    for row in rows:
        assert set(row.keys()) == set(REQUIRED_FIELDS), row
        for field in REQUIRED_FIELDS:
            assert row[field] is not None, f"{row.get('dataset_or_material')} missing {field}"


def test_no_duplicate_source_dataset_records():
    rows = _read_rows()
    seen = set()
    for row in rows:
        key = (row["source_organization"], row["dataset_or_material"])
        assert key not in seen, f"duplicate inventory record: {key}"
        seen.add(key)


def test_every_primary_source_has_a_real_official_url():
    rows = _read_rows()
    for row in rows:
        if row["record_type"] == "primary_source":
            url = row["official_url"].strip()
            assert url, f"primary_source {row['dataset_or_material']} has no official_url"
            assert url.startswith("http"), (
                f"primary_source {row['dataset_or_material']} official_url "
                f"doesn't look like a URL: {url!r}"
            )


def test_priority_values_are_from_the_defined_scale():
    rows = _read_rows()
    for row in rows:
        assert row["priority"] in VALID_PRIORITIES, row["priority"]


def test_historical_classification_values_are_from_the_defined_set():
    rows = _read_rows()
    for row in rows:
        assert row["historical_classification"] in VALID_CLASSIFICATIONS, row["historical_classification"]


def test_record_type_values_are_from_the_defined_set():
    rows = _read_rows()
    for row in rows:
        assert row["record_type"] in VALID_RECORD_TYPES, row["record_type"]


def test_all_six_primary_organizations_named_in_the_task_are_present():
    rows = _read_rows()
    orgs = {row["source_organization"] for row in rows if row["record_type"] == "primary_source"}
    missing = PRIMARY_ORGS_REQUIRED - orgs
    assert not missing, f"missing primary organizations: {missing}"


def test_at_least_one_p0_record_exists():
    rows = _read_rows()
    assert any(row["priority"] == "P0" for row in rows)


def test_unverified_fields_use_the_exact_placeholder_not_a_guess():
    """
    Every field left unverified must use the exact string 'Unknown /
    Requires verification' -- catches an accidental blank cell, which
    would silently look like 'nothing was recorded' rather than
    'explicitly marked unverified' (this task's core honesty
    requirement).
    """
    rows = _read_rows()
    for row in rows:
        for field in REQUIRED_FIELDS:
            if field in ("official_url", "source_organization", "dataset_or_material",
                         "record_type", "priority", "historical_classification"):
                continue
            assert row[field] != "", (
                f"{row['dataset_or_material']}.{field} is blank -- use "
                f"'Unknown / Requires verification' instead of an empty cell"
            )
