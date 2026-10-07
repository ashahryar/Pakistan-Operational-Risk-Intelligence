from __future__ import annotations

from fastapi import APIRouter

from api.app.services.freshness import freshness

router = APIRouter(prefix="/api/v1/freshness", tags=["freshness"])


@router.get("")
def get_freshness():
    """Latest data date, last ingestion and ingestion/source state per domain, read from the database on every request. Read-only."""
    return freshness()
