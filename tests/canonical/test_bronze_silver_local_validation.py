"""Task 20 -- tests for the pure-Python Bronze/Silver contract validation
(databricks/src/common/local_validation.py) and the canonical domain registry
(pipeline/canonical/domain_registry.py). No pyspark required (these are not the Spark tests --
see databricks/tests/test_canonical_bronze_silver.py for the pyspark-gated ones). The autouse
guard in tests/canonical/conftest.py prevents any accidental real dq.quarantine write.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from databricks.src.common.local_validation import bronze_dedupe, bronze_validate, run_bronze_silver, silver_validate
from pipeline.canonical.domain_registry import DOMAIN_REGISTRY, assert_registry_matches_contracts
from pipeline.canonical.tier1_adapters import adapt_ffc_reservoir
from scripts.parsing.tier1 import ffc_reservoir
from scripts.parsing.tier1.artifacts import Artifact, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rec(**overrides):
    base = {"domain": "rainfall_observation", "source": "pdma", "source_record_id": "r1",
            "ingestion_timestamp": "2026-09-01T00:00:00+00:00",
            "provenance": {"source_organization": "PDMA", "source_dataset": "rainfall_report",
                           "parser_version": "1.0.0", "normalization_version": "1.0.0"},
            "observed_at": "2026-09-01T00:00:00+00:00", "rainfall_amount": 12.5}
    base.update(overrides)
    return base


# ---------------------------------------------------------------- domain registry
def test_domain_registry_matches_contracts_bronze_and_silver_definitions():
    assert assert_registry_matches_contracts() == []


def test_every_registry_domain_has_a_non_empty_source_adapter_list():
    for domain, spec in DOMAIN_REGISTRY.items():
        assert spec.source_adapters, f"{domain} has no documented source adapter"


# ---------------------------------------------------------------- bronze_dedupe
def test_bronze_dedupe_keeps_latest_ingestion_timestamp_for_duplicate_key():
    older = _rec(ingestion_timestamp="2026-09-01T00:00:00+00:00", rainfall_amount=10.0)
    newer = _rec(ingestion_timestamp="2026-09-02T00:00:00+00:00", rainfall_amount=99.0)
    result = bronze_dedupe([older, newer])
    assert len(result) == 1 and result[0]["rainfall_amount"] == 99.0


def test_bronze_dedupe_is_a_no_op_on_distinct_keys():
    a, b = _rec(source_record_id="a"), _rec(source_record_id="b")
    assert len(bronze_dedupe([a, b])) == 2


def test_bronze_dedupe_duplicate_injection_causes_no_row_multiplication():
    recs = [_rec(source_record_id=str(i)) for i in range(5)]
    doubled = recs + recs
    assert len(bronze_dedupe(doubled)) == len(bronze_dedupe(recs)) == 5


# ---------------------------------------------------------------- bronze_validate
def test_bronze_validate_flags_missing_source_record_id():
    bad = _rec(source_record_id=None)
    result = bronze_validate([_rec(), bad])
    assert result["valid"] == 1 and len(result["invalid"]) == 1
    assert "missing_source_record_id" in result["invalid"][0]["errors"]


def test_bronze_validate_flags_missing_provenance_field():
    bad = _rec()
    bad["provenance"] = dict(bad["provenance"])
    bad["provenance"]["parser_version"] = None
    result = bronze_validate([bad])
    assert "missing_provenance_parser_version" in result["invalid"][0]["errors"]


# ---------------------------------------------------------------- silver_validate
def test_silver_validate_flags_fully_null_required_fields():
    bad = _rec(rainfall_amount=None)
    result = silver_validate([bad], "rainfall_observation")
    assert result["fully_null_required_rows"] == ["r1"] and result["passed"] == 0


def test_silver_validate_does_not_flag_a_legitimate_zero():
    zero = _rec(rainfall_amount=0.0)
    result = silver_validate([zero], "rainfall_observation")
    assert result["fully_null_required_rows"] == [] and result["passed"] == 1


def test_silver_validate_date_only_timestamp_parses_cleanly():
    rec = _rec(observed_at="2026-09-17")
    result = silver_validate([rec], "rainfall_observation")
    assert result["unparseable_timestamps"] == []


def test_silver_validate_flags_a_genuinely_unparseable_timestamp():
    rec = _rec(observed_at="not-a-date")
    result = silver_validate([rec], "rainfall_observation")
    assert result["unparseable_timestamps"][0]["field"] == "observed_at"


def test_silver_validate_rejects_unregistered_domain():
    with pytest.raises(ValueError, match="no Silver transformation registered"):
        silver_validate([_rec()], "not_a_real_domain")


# ---------------------------------------------------------------- end-to-end, with real adapter output
def test_run_bronze_silver_end_to_end_on_real_ffc_reservoir_fixture():
    fixture = REPO_ROOT / "tests" / "tier1" / "fixtures" / "raw" / "ffc" / "homepage.html"
    artifact = Artifact(fixture, sha256_file(fixture), "https://ffc.gov.pk", "2026-09-16T10:00:00+00:00",
                        "reservoir_levels", "ffc")
    parsed, _ = ffc_reservoir.parse_reservoir_html(artifact)
    canonical = adapt_ffc_reservoir(parsed, quarantine=lambda **kw: True)

    result = run_bronze_silver(canonical, "reservoir_observation")
    assert result["input_records"] == result["bronze_unique_records"] == 3  # Tarbela/Mangla/Chashma
    assert result["bronze"]["invalid"] == [] and result["silver"]["fully_null_required_rows"] == []
    for record in canonical:
        assert record["provenance"]["source_file"] and record["provenance"]["sha256"]  # Tier-1 provenance survives


def test_run_bronze_silver_is_idempotent_on_real_canonical_jsonl_if_present():
    """If scripts/lakehouse/validate_lakehouse.py has already been run, exercise it against the
    real on-disk canonical JSONL -- otherwise this is a clean skip, not a failure (no synthetic
    data is substituted for the real-fixture check Task 20 requires)."""
    path = REPO_ROOT / "data" / "parsed" / "canonical" / "reservoir_observation" / "tier1_ffc.jsonl"
    if not path.exists():
        pytest.skip("data/parsed/canonical/ not yet generated in this environment")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    first = run_bronze_silver(records, "reservoir_observation")
    second = run_bronze_silver(records, "reservoir_observation")
    assert first["bronze_unique_records"] == second["bronze_unique_records"]
    assert first["silver"]["passed"] == second["silver"]["passed"]
