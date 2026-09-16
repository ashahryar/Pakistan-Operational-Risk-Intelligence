"""
tests/architecture/test_codebase_audit.py

Task 16 (Phase 1 / ADR-0001) -- lightweight validation of the audit
artifacts (docs/architecture/CODEBASE_AUDIT.md, codebase_audit.csv)
produced by the read-only codebase audit. These tests validate the
audit's own internal consistency and factual grounding (every
referenced file really exists, every status/severity is a recognized
value, no duplicate rows) -- they do not re-run the audit's findings
or assert anything about the correctness of the audited code itself.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "docs" / "architecture" / "codebase_audit.csv"
MD_PATH = PROJECT_ROOT / "docs" / "architecture" / "CODEBASE_AUDIT.md"

REQUIRED_COLUMNS = [
    "file", "folder", "component_type", "source", "purpose", "used_by",
    "status", "severity", "input", "output", "database_dependency",
    "test_coverage", "finding", "recommended_action",
]

VALID_STATUS = {
    "CORRECT", "CORRECT_WITH_MINOR_ISSUE", "NEEDS_FIX", "BROKEN",
    "DEAD_UNUSED", "DUPLICATE", "NOT_IMPLEMENTED",
}
VALID_SEVERITY = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    assert CSV_PATH.exists(), f"audit CSV missing: {CSV_PATH}"
    with open(CSV_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_csv_exists_and_parses(rows):
    assert len(rows) > 0, "audit CSV parsed to zero rows"


def test_required_columns_present(rows):
    for row in rows:
        for col in REQUIRED_COLUMNS:
            assert col in row, f"missing column {col!r} in a CSV row"


def test_no_duplicate_file_rows(rows):
    files = [r["file"] for r in rows]
    seen = set()
    dupes = set()
    for f in files:
        if f in seen:
            dupes.add(f)
        seen.add(f)
    assert not dupes, f"duplicate file rows in audit CSV: {sorted(dupes)}"


def test_status_values_are_valid(rows):
    bad = [(r["file"], r["status"]) for r in rows if r["status"] not in VALID_STATUS]
    assert not bad, f"invalid status values: {bad}"


def test_severity_values_are_valid(rows):
    bad = [(r["file"], r["severity"]) for r in rows if r["severity"] not in VALID_SEVERITY]
    assert not bad, f"invalid severity values: {bad}"


def test_every_referenced_file_actually_exists(rows):
    """
    This is the check that catches the historical failure class named
    explicitly in Task 16's instructions (a DAG/script referencing a
    file that doesn't actually exist on disk).
    """
    missing = [r["file"] for r in rows if not (PROJECT_ROOT / r["file"]).exists()]
    assert not missing, f"audit CSV references files that don't exist on disk: {missing}"


def test_no_correct_status_with_high_or_critical_severity(rows):
    """A file marked fully CORRECT should not simultaneously carry a
    HIGH/CRITICAL severity finding -- that combination would mean the
    audit contradicts itself."""
    bad = [
        r["file"] for r in rows
        if r["status"] == "CORRECT" and r["severity"] in ("HIGH", "CRITICAL")
    ]
    assert not bad, f"CORRECT rows with HIGH/CRITICAL severity: {bad}"


def test_no_dead_or_not_implemented_with_critical_severity(rows):
    """Code that is confirmed dead/unreferenced or an empty stub cannot
    be CRITICAL to the running system by definition -- if it were, it
    wouldn't be dead."""
    bad = [
        r["file"] for r in rows
        if r["status"] in ("DEAD_UNUSED", "NOT_IMPLEMENTED") and r["severity"] == "CRITICAL"
    ]
    assert not bad, f"DEAD_UNUSED/NOT_IMPLEMENTED rows marked CRITICAL: {bad}"


def test_report_contains_all_major_project_areas(rows):
    """Confirms the CSV inventory actually covers every folder Task 16
    named as must-inspect, not just a subset."""
    folders = {r["folder"] for r in rows}
    expected_prefixes = [
        "scripts/extraction", "scripts/parsing", "scripts/database",
        "scripts/warehouse", "scripts/risk_engine", "scripts/geo",
        "scripts/forecasting", "scripts/acquisition", "scripts/audit",
        "pipeline/dags", "pipeline/helpers", "pipeline/utils", "pipeline/sensors",
        "pipeline/config", "dashboard", "config", "aws", "validation", "tests",
    ]
    for prefix in expected_prefixes:
        matched = any(f == prefix or f.startswith(prefix + "/") for f in folders)
        assert matched, f"no CSV row found under expected area {prefix!r}"


def test_markdown_report_exists_and_has_required_sections():
    assert MD_PATH.exists(), f"audit markdown report missing: {MD_PATH}"
    text = MD_PATH.read_text(encoding="utf-8")
    required_headings = [
        "Executive Summary",
        "Folder-by-folder Audit",
        "Script-level Findings",
        "Parser Audit",
        "Extraction Audit",
        "Database/Loader Audit",
        "DAG Audit",
        "Dashboard Audit",
        "End-to-End Compatibility",
        "Critical Issues",
        "Minor Issues",
        "Dead/Duplicate Code",
        "Recommended Fix Order",
    ]
    missing = [h for h in required_headings if h not in text]
    assert not missing, f"markdown report is missing required sections: {missing}"


def test_markdown_report_mentions_every_required_source():
    text = MD_PATH.read_text(encoding="utf-8")
    required_sources = [
        "NDMA", "PDMA Punjab", "PDMA Sindh", "PDMA KP", "PDMA Balochistan",
        "PMD", "SUPARCO", "AQI Punjab", "FFC",
    ]
    missing = [s for s in required_sources if s not in text]
    assert not missing, f"markdown report never mentions these required sources: {missing}"


def test_dead_and_broken_counts_are_internally_consistent(rows):
    """Sanity check: the counts reported in the final summary must be
    derivable from the CSV itself, not invented separately. This test
    doesn't check the markdown's prose numbers (those are asserted by
    hand against this same query at report-writing time) -- it just
    guards against the CSV being empty or degenerate for any one
    status bucket that the report's executive summary depends on."""
    from collections import Counter
    counts = Counter(r["status"] for r in rows)
    # every status value that appears anywhere in VALID_STATUS should be
    # representable -- but not every value must be non-zero (e.g. a repo
    # could in principle have zero DUPLICATE files). We only assert the
    # buckets we know are non-empty from the audit narrative.
    for expected_nonzero in ("CORRECT", "DEAD_UNUSED", "NEEDS_FIX", "BROKEN", "DUPLICATE", "NOT_IMPLEMENTED"):
        assert counts.get(expected_nonzero, 0) > 0, (
            f"expected at least one {expected_nonzero} row based on the audit's own findings, found none"
        )
