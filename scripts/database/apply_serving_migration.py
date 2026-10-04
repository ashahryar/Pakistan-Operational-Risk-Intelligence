"""Task 26 -- apply / roll back the geographic serving-layer migration (db/migrations/0026*.sql).

Additive and idempotent ('up'); 'down' removes only the objects 'up' created. Each file runs in ONE transaction
(PostgreSQL DDL is transactional), so a failure leaves the database unchanged.
CLAUDE.md rule 2: take and restore-verify a fresh pg_dump before running 'up' against the live database.

Usage:
  python scripts/database/apply_serving_migration.py up [--postgis] [--database NAME]
  python scripts/database/apply_serving_migration.py down [--postgis] [--database NAME]
--postgis additionally applies/rolls back 0026b (a guarded no-op when PostGIS is not available on the server).
--database lets the migration be exercised against a scratch copy instead of the live database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MIGRATIONS = PROJECT_ROOT / "db" / "migrations"
BASE = "0026_geo_serving_layer"
POSTGIS = "0026b_postgis_geometry"


def engine_for(database: Optional[str] = None) -> Engine:
    """The project engine, or the same server/credentials pointed at another database (e.g. a scratch copy)."""
    from config.database import DATABASE_URL, engine
    if not database:
        return engine
    from sqlalchemy.engine import make_url
    return create_engine(make_url(DATABASE_URL).set(database=database))


def sql_files(direction: str, with_postgis: bool) -> list[Path]:
    up = direction == "up"
    names = [BASE] + ([POSTGIS] if with_postgis else [])
    if not up:
        names = list(reversed(names))
    return [MIGRATIONS / f"{n}.{direction}.sql" for n in names]


def run_sql(eng: Engine, sql: str) -> None:
    with eng.begin() as conn:
        conn.exec_driver_sql(sql.replace("%", "%%"))


def apply(direction: str, with_postgis: bool = False, database: Optional[str] = None) -> list[str]:
    eng = engine_for(database)
    done = []
    for f in sql_files(direction, with_postgis):
        run_sql(eng, f.read_text(encoding="utf-8"))
        done.append(f.name)
    return done


def objects_present(eng: Engine) -> dict[str, bool]:
    q = text("""SELECT to_regclass('geo.boundary_source') IS NOT NULL, to_regclass('geo.boundary_admin_unit') IS NOT NULL,
                       to_regclass('geo.boundary_crosswalk') IS NOT NULL, to_regclass('risk.operational_risk') IS NOT NULL,
                       to_regclass('risk.latest_operational_risk') IS NOT NULL, to_regclass('geo.operational_risk_map') IS NOT NULL,
                       to_regclass('geo.current_boundary') IS NOT NULL""")
    with eng.connect() as conn:
        r = conn.execute(q).fetchone()
    keys = ["geo.boundary_source", "geo.boundary_admin_unit", "geo.boundary_crosswalk", "risk.operational_risk",
            "risk.latest_operational_risk", "geo.operational_risk_map", "geo.current_boundary"]
    return dict(zip(keys, r))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("direction", choices=["up", "down"])
    ap.add_argument("--postgis", action="store_true")
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    print("applied:", apply(a.direction, a.postgis, a.database))
    print(objects_present(engine_for(a.database)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
