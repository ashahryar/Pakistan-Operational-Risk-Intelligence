"""
databricks/src/common/local_validation.py

Task 20 -- a deterministic, pure-Python stand-in for the real Spark Bronze/Silver transformations
in databricks/src/{bronze,silver}/canonical_*.py, for environments without pyspark (confirmed
not installed here -- see databricks/README.md). This module does NOT execute Spark and never
claims to: it reuses the exact same per-domain configuration the real Spark modules define
(BRONZE_KEY_COLUMNS/BRONZE_ORDER_BY, _TIMESTAMP_COLUMNS, _REQUIRED_NON_NULL_ANY -- imported, not
duplicated) and performs the equivalent logical operations in plain Python, so the same canonical
JSONL can be checked for Bronze/Silver contract compliance today, and the exact same Spark code
can be run unmodified once pyspark is available (e.g. in CI or a real Databricks environment).

What this validates (STEP 6/9 of Task 20):
  - bronze_dedupe(): the same (domain, source, source_record_id) identity, latest
    ingestion_timestamp wins, that deduplicate_by_key() implements via a Spark window function.
  - bronze_validate(): every record carries the four REQUIRED provenance/contract fields
    (reusing pipeline.canonical.contracts.validate_record -- not a second rule set).
  - silver_validate(): the domain's required-any-non-null guard (the same check
    assert_no_fully_null_rows performs) and whether each configured timestamp column, if present,
    is a string Spark's to_timestamp() could actually parse (ISO 8601 or a bare date) --
    approximated here via datetime.fromisoformat, which accepts the same two string shapes
    normalize_timestamp() ever produces.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from databricks.src.bronze.canonical_bronze import BRONZE_KEY_COLUMNS, BRONZE_ORDER_BY
from databricks.src.silver.canonical_silver import _REQUIRED_NON_NULL_ANY, _TIMESTAMP_COLUMNS
from pipeline.canonical.contracts import validate_record


def bronze_dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Python equivalent of deduplicate_by_key(df, BRONZE_KEY_COLUMNS, BRONZE_ORDER_BY): one row
    per key, the row with the greatest BRONZE_ORDER_BY value wins (ties broken by input order,
    matching Spark's row_number() over a deterministic partition+order when values tie)."""
    best: dict[tuple, tuple[str, int, dict]] = {}
    for index, record in enumerate(records):
        key = tuple(record.get(col) for col in BRONZE_KEY_COLUMNS)
        rank = (record.get(BRONZE_ORDER_BY) or "", index)
        current = best.get(key)
        if current is None or rank >= (current[0], current[1]):
            best[key] = (rank[0], rank[1], record)
    return [item[2] for item in best.values()]


def bronze_validate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Bronze-layer contract check: required provenance/contract fields only (no typing, no
    business rules -- Bronze is near-verbatim, per Task 18/20's explicit requirement)."""
    invalid = []
    for record in records:
        errors = [e for e in validate_record(record) if e.startswith("missing_") and
                 ("provenance" in e or e.split("_", 1)[1] in ("source", "source_record_id", "ingestion_timestamp"))]
        if errors:
            invalid.append({"source_record_id": record.get("source_record_id"), "errors": errors})
    return {"total": len(records), "valid": len(records) - len(invalid), "invalid": invalid}


def _timestamp_parses(value: Any) -> bool:
    if value is None:
        return True  # null is valid -- never fabricated, never a parse failure
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def silver_validate(records: list[dict[str, Any]], domain: str) -> dict[str, Any]:
    """Silver-layer contract check for one domain's (already bronze-deduplicated) records:
    required-any-non-null guard + timestamp-column parseability. Mirrors to_silver()'s own two
    checks (databricks/src/silver/canonical_silver.py), executed in pure Python."""
    if domain not in _TIMESTAMP_COLUMNS:
        raise ValueError(f"no Silver transformation registered for domain {domain!r}")

    required_any = _REQUIRED_NON_NULL_ANY.get(domain, ())
    fully_null_rows = [r.get("source_record_id") for r in records
                       if required_any and all(r.get(f) is None for f in required_any)]
    bad_timestamps = [{"source_record_id": r.get("source_record_id"), "field": f, "value": r.get(f)}
                      for r in records for f in _TIMESTAMP_COLUMNS[domain]
                      if f in r and not _timestamp_parses(r.get(f))]

    return {"total": len(records), "fully_null_required_rows": fully_null_rows,
            "unparseable_timestamps": bad_timestamps,
            "passed": len(records) - len(fully_null_rows)}


def run_bronze_silver(records: list[dict[str, Any]], domain: str) -> dict[str, Any]:
    """End-to-end local stand-in for load_canonical_to_bronze() -> to_silver()."""
    deduped = bronze_dedupe(records)
    bronze = bronze_validate(deduped)
    silver = silver_validate(deduped, domain)
    return {"domain": domain, "input_records": len(records), "bronze_unique_records": len(deduped),
           "duplicates_removed": len(records) - len(deduped), "bronze": bronze, "silver": silver}
