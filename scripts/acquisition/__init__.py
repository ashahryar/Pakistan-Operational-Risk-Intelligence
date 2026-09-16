"""
scripts/acquisition

Phase 1 / Task 15 (ADR-0001) -- the raw national data acquisition
layer: official source -> HTTP fetch -> validation -> immutable raw
artifact -> provenance manifest -> (failure -> local failure log).

This package does NOT parse, normalize, or transform any acquired
content, and does NOT touch PostgreSQL or AWS. It reuses
scripts/extraction/common/fetcher.py's HTTPClient for the underlying
HTTP session/retry mechanics rather than re-implementing retry logic
that already exists in the repo.
"""
