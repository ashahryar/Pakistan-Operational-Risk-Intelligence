"""
tests/acquisition/test_manifest.py

Phase 1 / Task 15 (ADR-0001) -- deterministic tests for
scripts/acquisition/manifest.py. tmp_path only -- no live DB, no
network, no writes under the real data/raw/manifests/ tree.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.acquisition.manifest import (
    REQUIRED_FIELDS,
    append_manifest_record,
    build_manifest_record,
    read_manifest,
    write_summary,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sample_record(**overrides):
    base = dict(
        source_organization="suparco", dataset="disasterwatch",
        source_url="https://example.gov.pk/api/x", endpoint="/api/x",
        retrieved_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        http_status=200, content_type="application/json",
        local_path=Path("/tmp/x.json"), filename="x.json",
        sha256="a" * 64, byte_size=123, acquisition_method="http_get_json",
        classification="LIVE_CURRENT", historical_or_current="current",
        geographic_scope="National", verification_status="VERIFIED",
    )
    base.update(overrides)
    return build_manifest_record(**base)


def test_build_manifest_record_has_every_required_field():
    record = _sample_record()
    assert set(REQUIRED_FIELDS).issubset(record.keys())


def test_build_manifest_record_sha256_is_valid_hex():
    record = _sample_record(sha256="b" * 64)
    assert _SHA256_RE.match(record["sha256"])


def test_build_manifest_record_retrieved_at_is_iso_format():
    record = _sample_record()
    # Must round-trip through datetime.fromisoformat without error.
    parsed = datetime.fromisoformat(record["retrieved_at"])
    assert parsed.year == 2026


def test_append_manifest_record_rejects_missing_fields():
    incomplete = {"source_organization": "x"}
    with pytest.raises(ValueError):
        append_manifest_record(incomplete)


def test_append_manifest_record_writes_jsonl_and_is_appendable(tmp_path):
    record1 = _sample_record(filename="a.json")
    record2 = _sample_record(filename="b.json")

    path1 = append_manifest_record(record1, manifest_dir=tmp_path)
    path2 = append_manifest_record(record2, manifest_dir=tmp_path)

    assert path1 == path2  # same (organization, dataset) -> same manifest file
    lines = path1.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["filename"] == "a.json"
    assert json.loads(lines[1])["filename"] == "b.json"


def test_append_manifest_record_never_truncates_existing_records(tmp_path):
    append_manifest_record(_sample_record(filename="a.json"), manifest_dir=tmp_path)
    append_manifest_record(_sample_record(filename="b.json"), manifest_dir=tmp_path)
    records = read_manifest(
        list(tmp_path.glob("*.jsonl"))[0]
    )
    assert len(records) == 2


def test_read_manifest_returns_empty_list_for_missing_file(tmp_path):
    assert read_manifest(tmp_path / "does_not_exist.jsonl") == []


def test_write_summary_produces_valid_json(tmp_path):
    summary = {"task": "Task 15", "total_artifacts": 3}
    path = write_summary(summary, path=tmp_path / "summary.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == summary
