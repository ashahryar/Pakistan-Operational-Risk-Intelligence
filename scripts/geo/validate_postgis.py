"""Task 26 -- validate the geographic serving layer in the database (read-only).

Reports server/PostGIS facts, boundary sources/rows/validity, crosswalk counts, canonical-geography preservation,
risk serving rows, latest risk date, status distribution and the geometry/risk join. Exit code 1 on any failure.

Usage: python scripts/geo/validate_postgis.py [--database NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402


def collect(database: Optional[str] = None) -> dict:
    from scripts.database.apply_serving_migration import engine_for
    q = lambda conn, sql: [dict(r._mapping) for r in conn.execute(text(sql))]  # noqa: E731
    out: dict = {"failures": []}
    with engine_for(database).connect() as conn:
        out["postgresql_version"] = conn.execute(text("SHOW server_version")).scalar_one()
        pg = q(conn, "SELECT name, installed_version FROM pg_available_extensions WHERE name = 'postgis'")
        out["postgis_available"] = bool(pg)
        out["postgis_installed_version"] = pg[0]["installed_version"] if pg else None
        out["boundary_geometry_storage"] = ("postgis geometry + geojson" if out["postgis_installed_version"] else "geojson jsonb (PostGIS not installed)")
        out["boundary_sources"] = q(conn, "SELECT source_key, dataset_name, publisher, dataset_version, valid_on::text, license, checksum, crs, "
                                          "government_certified FROM geo.boundary_source ORDER BY source_id")
        out["boundary_rows_by_level"] = {str(r["level"]): r["n"] for r in q(conn, "SELECT level, count(*) n FROM geo.boundary_admin_unit GROUP BY 1 ORDER BY 1")}
        v = q(conn, "SELECT count(*) FILTER (WHERE geometry_valid) valid, count(*) FILTER (WHERE NOT geometry_valid) invalid, "
                    "count(*) FILTER (WHERE geometry_geojson IS NULL) null_geom FROM geo.boundary_admin_unit")[0]
        out["geometry_valid"], out["geometry_invalid"], out["geometry_null"] = v["valid"], v["invalid"], v["null_geom"]
        out["crosswalk_by_level_status"] = {f"level{r['level']}:{r['match_status']}": r["n"] for r in q(
            conn, "SELECT b.level, c.match_status, count(*) n FROM geo.boundary_crosswalk c JOIN geo.boundary_admin_unit b USING (boundary_id) "
                  "GROUP BY 1, 2 ORDER BY 1, 2")}
        out["unmatched_boundary_units"] = q(conn, "SELECT count(*) n FROM geo.boundary_crosswalk WHERE match_status = 'unmatched'")[0]["n"]
        out["canonical_admin_units"] = {str(r["level"]): r["n"] for r in q(conn, "SELECT level, count(*) n FROM geo.admin_unit GROUP BY 1 ORDER BY 1")}
        out["risk_rows_current"] = q(conn, "SELECT count(*) n FROM risk.operational_risk WHERE is_current")[0]["n"]
        out["risk_rows_total"] = q(conn, "SELECT count(*) n FROM risk.operational_risk")[0]["n"]
        out["risk_rows_with_score"] = q(conn, "SELECT count(*) n FROM risk.operational_risk WHERE risk_score IS NOT NULL")[0]["n"]
        out["latest_risk_date"] = q(conn, "SELECT max(risk_date)::text d FROM risk.operational_risk WHERE is_current")[0]["d"]
        out["risk_status_distribution"] = {r["risk_status"]: r["n"] for r in q(
            conn, "SELECT risk_status, count(*) n FROM risk.operational_risk WHERE is_current GROUP BY 1 ORDER BY 1")}
        out["latest_risk_units"] = q(conn, "SELECT count(*) n FROM risk.latest_operational_risk")[0]["n"]
        m = q(conn, "SELECT count(*) units, count(geometry) with_geometry, count(*) FILTER (WHERE geometry IS NULL) without_geometry, "
                    "count(risk_status) with_risk, count(*) FILTER (WHERE geometry IS NULL AND risk_status IS NOT NULL) risk_without_geometry "
                    "FROM geo.operational_risk_map")[0]
        out["map_view"] = m
        out["indexes"] = [r["indexname"] for r in q(conn, "SELECT indexname FROM pg_indexes WHERE schemaname IN ('geo','risk') "
                                                          "AND (indexname LIKE 'ix\\_%') ORDER BY 1")]
    f = out["failures"]
    if out["geometry_invalid"] or out["geometry_null"]:
        f.append("invalid or null boundary geometry present")
    if out["risk_rows_current"] and out["latest_risk_units"] == 0:
        f.append("latest risk view is empty")
    if out["map_view"]["units"] != sum(n for lv, n in out["canonical_admin_units"].items() if lv in ("1", "2")):
        f.append("map view does not cover every canonical province/district exactly once")
    if out["map_view"]["with_risk"] != out["latest_risk_units"]:
        f.append("map view lost risk rows")
    if not out["boundary_sources"]:
        f.append("no boundary source loaded")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    out = collect(a.database)
    print(json.dumps(out, indent=2, default=str))
    return 1 if out["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
