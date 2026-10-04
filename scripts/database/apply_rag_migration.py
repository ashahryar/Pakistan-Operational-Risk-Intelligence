"""Task 29 -- apply / roll back db/migrations/0029_rag_foundation.*.sql (one transaction; additive; idempotent 'up').
CLAUDE.md rule 2: take and restore-verify a fresh pg_dump before running 'up' against the live database.

Usage: python scripts/database/apply_rag_migration.py up|down [--embeddings] [--database NAME]
  --embeddings  act on 0030_rag_chunk_embeddings (Task 30) instead of 0029; 'down' removes only rag.chunk_embeddings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.apply_serving_migration import engine_for, run_sql  # noqa: E402

FILE = PROJECT_ROOT / "db" / "migrations" / "0029_rag_foundation.{}.sql"
FILE_EMBEDDINGS = PROJECT_ROOT / "db" / "migrations" / "0030_rag_chunk_embeddings.{}.sql"


def apply(direction: str, database: Optional[str] = None, embeddings: bool = False) -> str:
    path = Path(str(FILE_EMBEDDINGS if embeddings else FILE).format(direction))
    run_sql(engine_for(database), path.read_text(encoding="utf-8"))
    return path.name


def tables_present(database: Optional[str] = None) -> dict[str, bool]:
    from sqlalchemy import text
    with engine_for(database).connect() as c:
        r = c.execute(text("SELECT to_regclass('rag.documents') IS NOT NULL, to_regclass('rag.document_chunks') IS NOT NULL")).fetchone()
        e = c.execute(text("SELECT to_regclass('rag.chunk_embeddings') IS NOT NULL")).scalar_one()
    return {"rag.documents": r[0], "rag.document_chunks": r[1], "rag.chunk_embeddings": e}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("direction", choices=["up", "down"])
    ap.add_argument("--database")
    ap.add_argument("--embeddings", action="store_true")
    a = ap.parse_args(argv)
    print("applied:", apply(a.direction, a.database, a.embeddings), tables_present(a.database))
    return 0


if __name__ == "__main__":
    sys.exit(main())
