"""
api/app/config.py

Task 16A (Phase 1 / ADR-0001) -- FastAPI foundation. Minimal settings
module; no secrets are defined here (DB credentials remain in
config.database, reused by api/app/db.py, not duplicated).
"""

API_TITLE = "Pakistan Operational Risk Intelligence API"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "Foundation API for PORI (Task 16A / ADR-0001). Serves only what "
    "the existing PostgreSQL database already reliably provides -- "
    "no endpoint here fabricates data. See docs/architecture/"
    "CODEBASE_AUDIT.md for the current, honest state of each "
    "underlying data source."
)
