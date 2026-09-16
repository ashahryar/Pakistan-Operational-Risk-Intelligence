"""
tests/acquisition/test_manifest_integrity.py

Phase 1 / Task 15 (ADR-0001) -- integration-style validation of the
REAL manifests and raw artifacts this task actually produced under
data/raw/manifests/ and data/raw/<org>/<dataset>/. Unlike
test_raw_store.py/test_manifest.py (pure logic, tmp_path only), this
file checks the genuine acquired evidence on disk. It is read-only --
never writes, never deletes, never touches PostgreSQL.

If no manifest has been produced yet (a fresh checkout that hasn't run
any acquire_*.py script), every test here is skipped rather than
failed -- this file validates real acquisition output when it exists,
it does not require acquisition to have run as a precondition for the
rest of the test suite.
"""

from __future__ import annotations

import json

import pytest

from config.path import RAW_DATA
from scripts.acquisition.manifest import MANIFEST_DIR, REQUIRED_FIELDS, read_manifest
from scripts.acquisition.raw_store import sha256_file

pytestmark = pytest.mark.skipif(
    not MANIFEST_DIR.exists() or not any(MANIFEST_DIR.glob("*.jsonl")),
    reason="no Task 15 acquisition manifests present yet -- run scripts/acquisition/run_tier1_acquisition.py first",
)


def _all_manifest_records():
    records = []
    for path in sorted(MANIFEST_DIR.glob("*.jsonl")):
        if path.name == "acquisition_failures.jsonl":
            continue
        records.extend(read_manifest(path))
    return records


def test_every_manifest_record_has_all_required_fields():
    for record in _all_manifest_records():
        for field in REQUIRED_FIELDS:
            assert field in record, f"{record.get('filename')} missing {field}"


def test_every_manifest_record_local_path_exists_on_disk():
    for record in _all_manifest_records():
        from pathlib import Path
        assert Path(record["local_path"]).exists(), f"manifest points to a missing file: {record['local_path']}"


def test_every_raw_artifact_is_non_zero_bytes():
    from pathlib import Path
    for record in _all_manifest_records():
        path = Path(record["local_path"])
        assert path.stat().st_size > 0, f"{path} is zero bytes"
        assert record["byte_size"] > 0


def test_every_manifest_checksum_matches_the_real_file_on_disk():
    """
    The single most important integrity check in this file: for every
    real acquired artifact, recompute its SHA-256 from the actual bytes
    on disk right now and confirm it matches what the manifest recorded
    at acquisition time. A mismatch would mean the file was altered
    after acquisition -- exactly what immutability is meant to prevent.
    """
    from pathlib import Path
    for record in _all_manifest_records():
        path = Path(record["local_path"])
        assert sha256_file(path) == record["sha256"], f"checksum mismatch for {path}"


def test_every_manifest_sha256_is_valid_hex_digest():
    for record in _all_manifest_records():
        assert len(record["sha256"]) == 64
        int(record["sha256"], 16)  # raises ValueError if not valid hex


def test_no_two_distinct_files_share_a_path_with_different_content():
    """
    Immutability sanity check: every local_path referenced by any
    manifest record must be internally consistent -- if the same path
    appears more than once (e.g. across repeated acquisition runs),
    every record for that path must report the same checksum, proving
    the file was never silently overwritten with different content.
    """
    from pathlib import Path
    seen: dict[str, str] = {}
    for record in _all_manifest_records():
        path = str(Path(record["local_path"]))
        if path in seen:
            assert seen[path] == record["sha256"], (
                f"{path} has conflicting checksums across manifest records -- "
                f"this would mean the raw artifact was overwritten"
            )
        else:
            seen[path] = record["sha256"]


def test_at_least_one_artifact_was_acquired_for_each_tier1_organization():
    """
    Confirms real acquisition happened for all four Tier 1
    organizations this task targeted (SUPARCO, EPA Punjab/AQI, FFC,
    PMD/NDMC) -- not just that the scripts exist.
    """
    orgs = {record["source_organization"] for record in _all_manifest_records()}
    expected = {"suparco", "epa_punjab", "ffc", "pmd_ndmc"}
    missing = expected - orgs
    assert not missing, f"no acquired artifacts found for: {missing}"
