"""
scripts/acquisition/failures.py

Phase 1 / Task 15 (ADR-0001) -- local, file-based acquisition-failure
log. Deliberately NOT the existing pipeline/utils/quarantine.py
mechanism: that writes to the live `dq.quarantine` Postgres table, and
Task 15 is scoped as a strictly local, file-based raw-acquisition layer
with zero PostgreSQL writes of any kind. This module is the acquisition
layer's equivalent -- same spirit (every failure is recorded, nothing
disappears silently), different, DB-free storage, exactly as the task
anticipates ("If useful, write failure metadata into a separate
acquisition-failure log").
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config.path import RAW_DATA

FAILURE_LOG_PATH = RAW_DATA / "manifests" / "acquisition_failures.jsonl"


def record_failure(
    *,
    source_organization: str,
    dataset: str,
    url: str,
    error_code: str,
    error_message: str,
    http_status: int | None,
    attempted_at: datetime,
) -> Path:
    """
    Appends one failure record. Never raises -- a failure to log a
    failure must not itself crash the acquisition run.
    """

    record = {
        "source_organization": source_organization,
        "dataset": dataset,
        "url": url,
        "error_code": error_code,
        "error_message": error_message,
        "http_status": http_status,
        "attempted_at": attempted_at.isoformat(),
    }

    try:
        FAILURE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FAILURE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass

    return FAILURE_LOG_PATH


def read_failures() -> list[dict]:
    if not FAILURE_LOG_PATH.exists():
        return []
    with open(FAILURE_LOG_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
