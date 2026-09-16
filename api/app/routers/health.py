from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from config.database import engine

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """
    Real connectivity check (SELECT 1), not a hardcoded "ok". Returns
    database=False (never raises) if the DB is unreachable -- a health
    endpoint that crashes when the thing it's checking is down is not
    useful to a monitoring system.
    """
    database_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
    }
