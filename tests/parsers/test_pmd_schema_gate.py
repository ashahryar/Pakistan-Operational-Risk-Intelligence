"""
tests/parsers/test_pmd_schema_gate.py

Task 16A (Phase 1 / ADR-0001), Part A item 4 -- PMD Data Quality
Validation Integration.

`validation/pmd/{schema,completeness,score}.py` existed but were never
imported by any production code (confirmed by the Task 16 codebase
audit, docs/architecture/CODEBASE_AUDIT.md) -- PMD had no
pipeline-level schema/quality gate, unlike NDMA (validation.ndma.*,
wired into parse_ndma.py) and PDMA (validation.pdma.*, wired into
parse_pdma.py). This task wires validation.pmd.schema's
validate_daily/validate_weekly/validate_alert into
scripts/parsing/pmd/pipeline.py, using the SAME quarantine
(pipeline.utils.quarantine.write_quarantine) and rejection-ratio gate
(config.data_quality.REJECTION_THRESHOLD, sys.exit(1)) mechanism Task
5 already built for NDMA/PDMA -- not a second validation framework.

These tests cover:
  - a schema-valid PMD record passes through unchanged
  - a schema-invalid PMD record is quarantined and dropped
  - the quarantine call carries the right source/domain/reason_code
  - the pipeline's overall rejection-ratio DQ gate still fires
    correctly (sys.exit(1)) once PMD's real rejections are included
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.parsing.pmd.pipeline as pmd_pipeline  # noqa: E402
from validation.pmd.schema import validate_daily, validate_weekly, validate_alert  # noqa: E402


VALID_DAILY_RECORD = {
    "city": "Lahore",
    "district": "Lahore",
    "province": "Punjab",
    "temperature": "34",
    "humidity": "45",
    "forecast_day_1": "Sunny",
    "forecast_day_2": "Partly Cloudy",
    "forecast_day_3": "Sunny",
    "category": "Hot",
    "scraped_at": "2026-09-16T10:00:00",
}

INVALID_DAILY_RECORD_MISSING_DISTRICT = {
    "city": "Mohenjo Daro",
    "district": None,  # the real, live gap this integration surfaced
    "province": "Sindh",
    "temperature": "38",
    "humidity": "20",
    "forecast_day_1": "Sunny",
    "forecast_day_2": "Sunny",
    "forecast_day_3": "Sunny",
    "category": "Hot",
    "scraped_at": "2026-09-16T10:00:00",
}


def _spy_quarantine(monkeypatch):
    calls = []

    def fake_write_quarantine(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(pmd_pipeline, "write_quarantine", fake_write_quarantine)
    return calls


# ==========================================================
# validation.pmd.schema itself -- confirms it is genuinely reachable
# and genuinely does what it claims, not just "imported somewhere"
# ==========================================================

def test_valid_pmd_daily_record_passes_schema_validation():
    is_valid, errors = validate_daily([VALID_DAILY_RECORD])
    assert is_valid is True
    assert errors == []


def test_invalid_pmd_daily_record_fails_schema_validation_with_a_specific_reason():
    is_valid, errors = validate_daily([INVALID_DAILY_RECORD_MISSING_DISTRICT])
    assert is_valid is False
    assert any("district" in e.lower() for e in errors)


# ==========================================================
# _apply_schema_gate -- the new integration point
# ==========================================================

def test_apply_schema_gate_keeps_valid_records_and_rejects_none(monkeypatch):
    calls = _spy_quarantine(monkeypatch)

    kept, additional_rejected = pmd_pipeline._apply_schema_gate(
        [VALID_DAILY_RECORD, VALID_DAILY_RECORD], validate_daily, "daily_forecast"
    )

    assert kept == [VALID_DAILY_RECORD, VALID_DAILY_RECORD]
    assert additional_rejected == 0
    assert calls == []


def test_apply_schema_gate_drops_and_quarantines_invalid_records(monkeypatch):
    calls = _spy_quarantine(monkeypatch)

    kept, additional_rejected = pmd_pipeline._apply_schema_gate(
        [VALID_DAILY_RECORD, INVALID_DAILY_RECORD_MISSING_DISTRICT],
        validate_daily,
        "daily_forecast",
    )

    assert kept == [VALID_DAILY_RECORD]
    assert additional_rejected == 1
    assert len(calls) == 1
    assert calls[0]["source"] == "pmd"
    assert calls[0]["domain"] == "daily_forecast"
    assert calls[0]["reason_code"] == "schema_invalid"
    assert calls[0]["raw_payload"] == INVALID_DAILY_RECORD_MISSING_DISTRICT
    assert "district" in calls[0]["message"].lower()


def test_apply_schema_gate_never_silently_drops_a_record_without_quarantining_it(monkeypatch):
    """Every record either survives into `kept` or is quarantined --
    never neither, per CLAUDE.md rule 6 ("no silent record dropping")."""
    calls = _spy_quarantine(monkeypatch)

    records = [VALID_DAILY_RECORD, INVALID_DAILY_RECORD_MISSING_DISTRICT, VALID_DAILY_RECORD]
    kept, additional_rejected = pmd_pipeline._apply_schema_gate(records, validate_daily, "daily_forecast")

    assert len(kept) + additional_rejected == len(records)
    assert len(kept) + len(calls) == len(records)


def test_apply_schema_gate_works_for_weekly_too(monkeypatch):
    calls = _spy_quarantine(monkeypatch)

    valid_weekly = {
        "date": "2026-09-16",
        "weekday": "Wednesday",
        "weather_summary": "Hot and dry",
        "regions": ["Punjab"],
        "category": "Hot",
        "scraped_at": "2026-09-16T10:00:00",
    }
    invalid_weekly = {**valid_weekly, "weather_summary": ""}

    kept, additional_rejected = pmd_pipeline._apply_schema_gate(
        [valid_weekly, invalid_weekly], validate_weekly, "weekly_outlook"
    )

    assert kept == [valid_weekly]
    assert additional_rejected == 1
    assert calls[0]["domain"] == "weekly_outlook"


# ==========================================================
# Full pipeline DQ gate -- proves the SAME existing rejection-ratio
# mechanism (config.data_quality.REJECTION_THRESHOLD, sys.exit(1))
# fires once schema-gate rejections are folded into the total, exactly
# like it already does for NDMA/PDMA.
# ==========================================================

def test_pipeline_dq_gate_fires_when_schema_rejections_push_ratio_over_threshold(monkeypatch, tmp_path):
    calls = _spy_quarantine(monkeypatch)

    # 1 valid + 3 invalid daily records -> 75% rejection, well over the
    # 15% REJECTION_THRESHOLD -- must sys.exit(1), matching NDMA/PDMA's
    # existing, already-tested gate behavior (Task 5).
    daily_records = [
        VALID_DAILY_RECORD,
        INVALID_DAILY_RECORD_MISSING_DISTRICT,
        INVALID_DAILY_RECORD_MISSING_DISTRICT,
        INVALID_DAILY_RECORD_MISSING_DISTRICT,
    ]

    monkeypatch.setattr(pmd_pipeline, "parse_daily_forecast", lambda: (daily_records, len(daily_records), 0))
    monkeypatch.setattr(pmd_pipeline, "parse_weekly_outlook", lambda: ([], 0, 0))
    monkeypatch.setattr(pmd_pipeline, "parse_weather_alert", lambda: {
        "alert_type": "Heatwave", "severity": "High", "duration": "3 days",
        "regions": ["Sindh"], "forecast": "Extreme heat expected",
        "category": "Warning", "scraped_at": "2026-09-16T10:00:00",
    })
    monkeypatch.setattr(pmd_pipeline, "OUTPUT_DIR", tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        pmd_pipeline.main()

    assert exc_info.value.code == 1
    # 3 schema-invalid daily records must each have been quarantined
    assert sum(1 for c in calls if c["domain"] == "daily_forecast") == 3


def test_pipeline_does_not_exit_when_all_pmd_records_are_valid(monkeypatch, tmp_path):
    _spy_quarantine(monkeypatch)

    monkeypatch.setattr(pmd_pipeline, "parse_daily_forecast", lambda: ([VALID_DAILY_RECORD], 1, 0))
    monkeypatch.setattr(pmd_pipeline, "parse_weekly_outlook", lambda: ([], 0, 0))
    monkeypatch.setattr(pmd_pipeline, "parse_weather_alert", lambda: {
        "alert_type": "Heatwave", "severity": "High", "duration": "3 days",
        "regions": ["Sindh"], "forecast": "Extreme heat expected",
        "category": "Warning", "scraped_at": "2026-09-16T10:00:00",
    })
    monkeypatch.setattr(pmd_pipeline, "OUTPUT_DIR", tmp_path)

    # Should not raise SystemExit -- if it does, the test itself fails.
    pmd_pipeline.main()
