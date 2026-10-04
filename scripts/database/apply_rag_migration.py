"""Task 29 -- apply / roll back db/migrations/0029_rag_foundation.*.sql (one transaction; additive; idempotent 'up').
CLAUDE.md rule 2: take and restore-verify a fresh pg_dump before running 'up' against the live database.

Usage: python scripts/database/apply_rag_migration.py up|down [--database NAME]
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


def apply(direction: str, database: Optional[str] = None) -> str:
    run_sql(engine_for(database), Path(str(FILE).format(direction)).read_text(encoding="utf-8"))
    return f"0029_rag_foundation.{direction}.sql"


def tables_present(database: Optional[str] = None) -> dict[str, bool]:
    from sqlalchemy import text
    with engine_for(database).connect() as c:
        r = c.execute(text("SELECT to_regclass('rag.documents') IS NOT NULL, to_regclass('rag.document_chunks') IS NOT NULL")).fetchone()
    return {"rag.documents": r[0], "rag.document_chunks": r[1]}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("direction", choices=["up", "down"])
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    print("applied:", apply(a.direction, a.database), tables_present(a.database))
    return 0


if __name__ == "__main__":
    sys.exit(main())
