"""
api/app/db.py

Task 16A (Phase 1 / ADR-0001) -- FastAPI foundation. Read-only query
helper reusing the project's existing config.database.engine (single
source of truth for the DB connection, not a second one) rather than
duplicating dashboard/db.py's Streamlit-specific caching layer.

Unlike dashboard/db.py's `_read_sql()` (which intentionally returns an
empty DataFrame on any failure so a Streamlit page keeps rendering),
an API has a better tool for "the request failed": a real HTTP error
status. A genuine database failure here raises `HTTPException(503)`
rather than silently returning an empty result -- an API client can
distinguish "no rows" (200, empty list) from "the database is
unreachable" (503) in a way a dashboard's DataFrame return value
cannot. An expected missing-table/column condition (the same
UndefinedTable/UndefinedColumn class dashboard/db.py now also
distinguishes) is treated as a 503 with a specific detail message,
never as a fabricated empty-but-successful 200.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from config.database import engine, redact_credentials

logger = logging.getLogger("api.db")


def fetch_all(query: str, params: dict | None = None) -> list[dict[str, Any]]:
    """
    Executes a read-only SQL query and returns a list of row dicts.
    Raises HTTPException(503) on any database failure -- never
    silently returns an empty/partial result for a failure that isn't
    genuinely "zero rows matched".
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return [dict(row._mapping) for row in result]
    except Exception as exc:
        safe_query = redact_credentials(query)
        safe_exc = redact_credentials(str(exc))
        logger.error("Query failed: %s\nSQL: %s", safe_exc, safe_query, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Database query failed -- see server logs for details.",
        ) from exc
