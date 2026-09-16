"""
scripts/acquisition/manifest.py

Phase 1 / Task 15 (ADR-0001) -- provenance manifest writer.

Every successful acquisition gets exactly one manifest record,
appended (never rewritten in place) to a newline-delimited JSON file
at data/raw/manifests/<organization>_<dataset>.jsonl -- one file per
(organization, dataset) pair, growing across runs, so the manifest
itself is as immutable/append-only as the raw artifacts it describes.

This module intentionally does NOT touch PostgreSQL -- Task 15 is a
strictly local, file-based raw-acquisition layer (see CLAUDE.md rule 2
and the task's explicit "zero PostgreSQL data changes" boundary).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.path import RAW_DATA

MANIFEST_DIR = RAW_DATA / "manifests"

REQUIRED_FIELDS = [
    "source_organization", "dataset", "source_url", "endpoint", "retrieved_at",
    "http_status", "content_type", "local_path", "filename", "sha256", "byte_size",
    "acquisition_method", "classification", "historical_or_current",
    "geographic_scope", "verification_status",
]


def build_manifest_record(
    *,
    source_organization: str,
    dataset: str,
    source_url: str,
    endpoint: Optional[str],
    retrieved_at: datetime,
    http_status: Optional[int],
    content_type: Optional[str],
    local_path: Path,
    filename: str,
    sha256: str,
    byte_size: int,
    acquisition_method: str,
    classification: str,
    historical_or_current: str,
    geographic_scope: str,
    verification_status: str,
    is_duplicate: bool = False,
) -> dict:
    """
    Builds one manifest record with exactly the fields the task
    specifies. Every field is given a real value or the documented
    'null' placeholder -- never fabricated.
    """

    return {
        "source_organization": source_organization,
        "dataset": dataset,
        "source_url": source_url,
        "endpoint": endpoint,
        "retrieved_at": retrieved_at.isoformat(),
        "http_status": http_status,
        "content_type": content_type,
        "local_path": str(local_path),
        "filename": filename,
        "sha256": sha256,
        "byte_size": byte_size,
        "acquisition_method": acquisition_method,
        "classification": classification,
        "historical_or_current": historical_or_current,
        "geographic_scope": geographic_scope,
        "verification_status": verification_status,
        "is_duplicate_retrieval": is_duplicate,
    }


def manifest_path_for(source_organization: str, dataset: str, manifest_dir: Path = MANIFEST_DIR) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    safe_org = source_organization.lower().replace(" ", "_").replace("/", "_")
    safe_dataset = dataset.lower().replace(" ", "_").replace("/", "_")
    return manifest_dir / f"{safe_org}_{safe_dataset}.jsonl"


def append_manifest_record(record: dict, manifest_dir: Path = MANIFEST_DIR) -> Path:
    """
    Appends `record` as one JSON line to its (organization, dataset)
    manifest file. Never rewrites or truncates the file -- each run's
    records simply accumulate.
    """

    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise ValueError(f"manifest record missing required fields: {missing}")

    path = manifest_path_for(record["source_organization"], record["dataset"], manifest_dir=manifest_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_summary(summary: dict, path: Optional[Path] = None) -> Path:
    path = path or (MANIFEST_DIR / "acquisition_summary.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return path
