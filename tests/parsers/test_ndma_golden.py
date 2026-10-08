"""
tests/parsers/test_ndma_golden.py

Phase 1 / Task 8 (ADR-0001) -- golden-file regression tests for
scripts/parsing/parse_ndma.py::parse_pdf(), run against real NDMA
sitrep PDFs already tracked under data/raw/ndma/.

5 fixtures, chosen for diversity of size/date/outcome (not
cherry-picked for a flattering result):
  - 6a3e702a90f23.pdf : currently quarantined (data/rejected/ndma/) --
    the one negative-path fixture, proving the rejection path still
    works today, not just the happy path.
  - 6a5b47ae2e9ea.pdf, 6a69c4ad9e9fa.pdf, 6a8c2c5119ae2.pdf,
    6a9bf0735e654.pdf : pass, spanning small/large/recent.

Expected-output JSON under tests/fixtures/expected/ndma/ was generated
by actually running the current parser against each of these 5 PDFs
and hand-reviewing the result -- it is NOT copied from
data/parsed/ndma/sitreps/, because at least one existing parsed file
there (6a3e702a90f23.json) predates Task 5's validation scoring and
does not reflect current parser behavior.

Isolation: this test never writes to the real data/parsed/ndma/ or
data/rejected/ndma/ directories (OUTPUT_FOLDER/REJECTED_FOLDER are
monkeypatched to a pytest tmp_path), and never writes to
dq.quarantine (write_quarantine is monkeypatched to an in-memory spy)
-- so running this suite touches neither tracked project data nor
PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.parsing.parse_ndma as parse_ndma

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NDMA_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ndma" / "reports" / "sitreps" / "all" / "pdfs"
EXPECTED_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "expected" / "ndma"

# Fields whose value legitimately differs on every run (wall-clock
# timestamps) and must be excluded from exact-match comparison.
VOLATILE_FIELDS = {"parsed_at"}

FIXTURES = [
    ("6a3e702a90f23.pdf", "rejected"),
    ("6a5b47ae2e9ea.pdf", "accepted"),
    ("6a69c4ad9e9fa.pdf", "accepted"),
    ("6a8c2c5119ae2.pdf", "accepted"),
    ("6a9bf0735e654.pdf", "accepted"),
]


def _run_parse_pdf(pdf_name, tmp_path, monkeypatch):
    pdf_path = NDMA_RAW_DIR / pdf_name
    if not pdf_path.exists():
        pytest.skip(f"fixture PDF not present (data/raw/ is gitignored, so it is absent from a clean clone): {pdf_path.name}")

    output_dir = tmp_path / "parsed"
    rejected_dir = tmp_path / "rejected"

    # Never write to the real data/parsed/ndma or data/rejected/ndma.
    monkeypatch.setattr(parse_ndma, "OUTPUT_FOLDER", output_dir)
    monkeypatch.setattr(parse_ndma, "REJECTED_FOLDER", rejected_dir)

    # Never write to the real dq.quarantine table.
    quarantine_calls = []

    def fake_write_quarantine(**kwargs):
        quarantine_calls.append(kwargs)
        return True

    monkeypatch.setattr(parse_ndma, "write_quarantine", fake_write_quarantine)

    result = parse_ndma.parse_pdf(pdf_path)

    saved_path = output_dir / f"{pdf_path.stem}.json"
    saved_data = None
    if saved_path.exists():
        with open(saved_path, encoding="utf-8") as f:
            saved_data = json.load(f)

    return result, saved_data, quarantine_calls


def _strip_volatile(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in VOLATILE_FIELDS}


@pytest.mark.parametrize("pdf_name,outcome", FIXTURES)
def test_ndma_parse_pdf_golden(pdf_name, outcome, tmp_path, monkeypatch):
    result, saved_data, quarantine_calls = _run_parse_pdf(pdf_name, tmp_path, monkeypatch)

    if outcome == "rejected":
        assert result["success"] is False
        assert saved_data is None, "a rejected PDF must not produce a saved parsed-JSON file"
        assert len(quarantine_calls) == 1, "exactly one rejection must be recorded"
        call = quarantine_calls[0]
        assert call["source"] == "ndma"
        assert call["domain"] == "sitrep"
        assert call["reason_code"] in ("schema_invalid", "quality_below_threshold")
        return

    assert result["success"] is True
    assert saved_data is not None, "an accepted PDF must produce a saved parsed-JSON file"
    assert quarantine_calls == [], "an accepted PDF must not write any quarantine record"

    expected_path = EXPECTED_DIR / f"{Path(pdf_name).stem}.json"
    assert expected_path.exists(), f"missing golden fixture: {expected_path}"
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert _strip_volatile(saved_data) == _strip_volatile(expected)


def test_ndma_golden_fixture_set_covers_both_outcomes():
    # Guards against someone silently deleting the one negative-path
    # fixture and leaving this suite happy-path-only.
    outcomes = {outcome for _, outcome in FIXTURES}
    assert outcomes == {"accepted", "rejected"}
