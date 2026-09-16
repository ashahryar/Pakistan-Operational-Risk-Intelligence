"""
scripts/acquisition/pipeline.py

Phase 1 / Task 15 (ADR-0001) -- the single "save this fetch result as a
manifested raw artifact, or record why it failed" step every
acquire_*.py script uses. Centralized so the write-verification safety
net in raw_store.save_raw_artifact() is exercised identically (and
failures are logged identically) everywhere, rather than each script
re-implementing its own try/except around save_raw_artifact().
"""

from __future__ import annotations

from typing import Optional

from scripts.acquisition.client import FetchResult
from scripts.acquisition.failures import record_failure
from scripts.acquisition.manifest import append_manifest_record, build_manifest_record
from scripts.acquisition.raw_store import save_raw_artifact


def save_fetch_result(
    *,
    result: FetchResult,
    source_organization: str,
    dataset: str,
    url: str,
    filename: str,
    acquisition_method: str,
    classification: str,
    historical_or_current: str,
    geographic_scope: str,
    endpoint: Optional[str] = None,
) -> dict:
    """
    Saves `result.content` as a raw artifact and appends its manifest
    record. If the on-disk write cannot be verified to match what was
    fetched (raw_store's own retry-then-raise safety net), this is
    treated exactly like any other acquisition failure: logged to the
    failure log, and NO manifest record is written -- a failed
    acquisition must never produce a successful manifest entry.

    Returns a dict describing the outcome, in the same shape every
    acquire_*.py script already prints/aggregates:
        {"status": "ACQUIRED", "url", "local_path", "sha256",
         "byte_size", "is_duplicate", "http_status"}
      or
        {"status": "FAILED", "url", "error_code"}
    """

    try:
        artifact = save_raw_artifact(
            organization=source_organization, dataset=dataset,
            retrieved_at=result.retrieved_at, filename=filename, content=result.content,
        )
    except (OSError, ValueError) as e:
        record_failure(
            source_organization=source_organization, dataset=dataset, url=url,
            error_code="write_verification_failed", error_message=str(e),
            http_status=result.http_status, attempted_at=result.retrieved_at,
        )
        return {"url": url, "status": "FAILED", "error_code": "write_verification_failed"}

    manifest_record = build_manifest_record(
        source_organization=source_organization, dataset=dataset, source_url=url, endpoint=endpoint,
        retrieved_at=result.retrieved_at, http_status=result.http_status, content_type=result.content_type,
        local_path=artifact.local_path, filename=artifact.filename, sha256=artifact.sha256,
        byte_size=artifact.byte_size, acquisition_method=acquisition_method,
        classification=classification, historical_or_current=historical_or_current,
        geographic_scope=geographic_scope, verification_status="VERIFIED", is_duplicate=artifact.is_duplicate,
    )
    append_manifest_record(manifest_record)

    return {
        "url": url, "status": "ACQUIRED", "local_path": str(artifact.local_path),
        "sha256": artifact.sha256, "byte_size": artifact.byte_size,
        "is_duplicate": artifact.is_duplicate, "http_status": result.http_status,
    }
