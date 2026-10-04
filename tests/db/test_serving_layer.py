"""Task 26 -- database tests for the geographic serving layer.

Static SQL checks always run. Live checks run against the real database when the serving layer exists. The rollback /
idempotency test runs against the scratch database `pori_t26_restore_check` (a restored copy of the pre-Task-26 backup) so
the live database is never rolled back; it is skipped if that scratch database is absent."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts.database.apply_serving_migration import apply, engine_for, objects_present

REPO = Path(__file__).resolve().parents[2]
MIG = REPO / "db" / "migrations"
UP = (MIG / "0026_geo_serving_layer.up.sql").read_text(encoding="utf-8")
DOWN = (MIG / "0026_geo_serving_layer.down.sql").read_text(encoding="utf-8")
UPB = (MIG / "0026b_postgis_geometry.up.sql").read_text(encoding="utf-8")
DOWNB = (MIG / "0026b_postgis_geometry.down.sql").read_text(encoding="utf-8")
SCRATCH = "pori_t26_restore_check"
NEW_OBJECTS = {"geo.operational_risk_map", "risk.latest_operational_risk", "geo.current_boundary", "risk.operational_risk",
               "geo.boundary_crosswalk", "geo.boundary_admin_unit", "geo.boundary_source"}


# ------------------------------------------------------------------ static (no database)
def test_migration_is_additive_only():
    stripped = re.sub(r"--[^\n]*", "", UP).upper()
    for forbidden in ("DROP ", "TRUNCATE", "DELETE ", "ALTER TABLE", "UPDATE "):
        assert forbidden not in stripped, forbidden
    created = re.findall(r"CREATE (?:OR REPLACE )?(?:TABLE|VIEW|SCHEMA|INDEX)(?: IF NOT EXISTS)? ([\w.]+)", UP, flags=re.I)
    assert all(re.search(r"CREATE (OR REPLACE VIEW|(TABLE|SCHEMA|INDEX) IF NOT EXISTS) " + re.escape(c), UP, re.I) for c in created)
    assert not any(c in {"geo.admin_unit", "geo.name_alias"} for c in created)
    for existing in ("geo.admin_unit", "geo.name_alias", "dq.quarantine"):
        assert not re.search(r"(INSERT INTO|UPDATE|DELETE FROM|ALTER TABLE|DROP TABLE)\s+" + re.escape(existing), UP, re.I)


def test_rollback_only_removes_task26_objects():
    dropped = set(re.findall(r"DROP (?:VIEW|TABLE) IF EXISTS ([\w.]+)", DOWN))
    assert dropped == NEW_OBJECTS
    assert "CASCADE" not in DOWN.upper()
    code = re.sub(r"--[^\n]*", "", DOWN)
    assert "geo.admin_unit" not in code and "quarantine" not in code.lower()
    assert "DROP COLUMN IF EXISTS geom" in DOWNB and "CREATE EXTENSION" not in DOWNB and "DROP EXTENSION" not in DOWNB


def test_postgis_migration_is_guarded_and_uses_a_spatial_index():
    assert "pg_available_extensions" in UPB and "RETURN" in UPB and "RAISE NOTICE" in UPB
    assert "geometry(MultiPolygon, 4326)" in UPB and "USING GIST (geom)" in UPB
    assert "ST_IsValid" in UPB and "ST_MakeValid" not in UPB          # validity is recorded, never repaired


def test_migrations_do_not_touch_aws_airflow_or_quarantine():
    for sql in (UP, DOWN, UPB, DOWNB):
        low = sql.lower()
        assert "quarantine" not in low and "s3" not in low and "dag" not in low


# ------------------------------------------------------------------ live database
def _live() -> bool:
    try:
        return objects_present(engine_for()).get("geo.operational_risk_map", False)
    except Exception:
        return False


live = pytest.mark.skipif(not _live(), reason="database / serving layer not available")


@pytest.fixture(scope="module")
def conn():
    with engine_for().connect() as c:
        yield c


def q(conn, sql, **p):
    return [dict(r._mapping) for r in conn.execute(text(sql), p)]


@live
def test_schema_and_objects_exist(conn):
    assert all(objects_present(engine_for()).values())
    assert q(conn, "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'risk'")


@live
def test_source_metadata_is_preserved(conn):
    import yaml
    cfg = yaml.safe_load((REPO / "config" / "admin_boundary_sources.yaml").read_text(encoding="utf-8"))
    src = cfg["sources"][cfg["active_source"]]
    s = q(conn, "SELECT * FROM geo.boundary_source")[0]
    assert "COD-AB" in s["dataset_name"] and "OCHA" in s["publisher"] and "CC BY-IGO" in s["license"]
    assert str(s["valid_on"]) == "2022-09-09" and s["dataset_version"].startswith("v01") and s["crs"] == "CRS84"
    assert s["checksum"] == src["archive_sha256"] and s["government_certified"] is False
    assert s["validation_json"]["valid"] is True and s["notes"]


@live
def test_boundary_geometry_exists_and_is_valid(conn):
    n = q(conn, "SELECT level, count(*) n, count(*) FILTER (WHERE geometry_valid) v, count(geometry_geojson) g FROM geo.boundary_admin_unit GROUP BY 1 ORDER BY 1")
    assert [(r["level"], r["n"], r["v"], r["g"]) for r in n] == [(1, 7, 7, 7), (2, 160, 160, 160)]
    g = q(conn, "SELECT geometry_geojson FROM geo.boundary_admin_unit WHERE name = 'Lahore'")[0]["geometry_geojson"]
    assert g["type"] in {"Polygon", "MultiPolygon"}
    assert not q(conn, "SELECT 1 FROM geo.boundary_admin_unit WHERE level = 2 AND parent_boundary_id IS NULL")     # hierarchy kept


@live
def test_crosswalk_statuses_are_preserved_and_unmatched_stay_visible(conn):
    c = {(r["level"], r["match_status"]): r["n"] for r in q(
        conn, "SELECT b.level, c.match_status, count(*) n FROM geo.boundary_crosswalk c JOIN geo.boundary_admin_unit b USING (boundary_id) GROUP BY 1, 2")}
    assert c == {(1, "exact"): 4, (1, "alias"): 3, (2, "exact"): 54, (2, "alias"): 2, (2, "unmatched"): 104}
    assert not q(conn, "SELECT 1 FROM geo.boundary_crosswalk WHERE match_status = 'unmatched' AND pori_admin_unit_id IS NOT NULL")
    assert not q(conn, "SELECT 1 FROM geo.boundary_crosswalk WHERE match_basis IS NULL OR source_id IS NULL")
    leah = q(conn, "SELECT c.match_status, c.match_basis, u.name FROM geo.boundary_crosswalk c JOIN geo.boundary_admin_unit b USING (boundary_id) "
                   "JOIN geo.admin_unit u ON u.id = c.pori_admin_unit_id WHERE b.name = 'Leiah'")[0]
    assert (leah["match_status"], leah["match_basis"], leah["name"]) == ("alias", "declared_crosswalk_alias", "Layyah")


@live
def test_canonical_geography_is_unchanged(conn):
    assert {r["level"]: r["n"] for r in q(conn, "SELECT level, count(*) n FROM geo.admin_unit GROUP BY 1")} == {0: 1, 1: 7, 2: 69}
    assert q(conn, "SELECT count(DISTINCT id) n, min(id) lo, max(id) hi FROM geo.admin_unit")[0] == {"n": 77, "lo": 1, "hi": 77}
    assert q(conn, "SELECT name FROM geo.admin_unit WHERE id = 2")[0]["name"] == "Punjab"
    assert not q(conn, "SELECT 1 FROM geo.admin_unit WHERE source LIKE '%cod%' OR source LIKE '%hdx%'")      # COD-AB never became canonical


@live
def test_canonical_geography_matches_the_pre_migration_backup_copy(conn):
    try:
        scratch = engine_for(SCRATCH).connect()
    except Exception:
        pytest.skip("scratch restore database not available")
    with scratch:
        sql = "SELECT md5(string_agg(id || '|' || level || '|' || name || '|' || coalesce(parent_id::text, ''), ',' ORDER BY id)) h FROM geo.admin_unit"
        assert q(conn, sql)[0]["h"] == q(scratch, sql)[0]["h"]


@live
def test_risk_records_are_preserved(conn):
    rows = [json.loads(x) for x in (REPO / "data" / "analytics" / "risk" / "gold_operational_risk.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    db = {(r["admin_unit_id"], str(r["risk_date"])): r for r in q(conn, "SELECT * FROM risk.operational_risk WHERE is_current")}
    assert len(db) == len(rows) and set(db) == {(r["admin_unit_id"], r["date"]) for r in rows}
    sample = rows[0]
    d = db[(sample["admin_unit_id"], sample["date"])]
    assert d["risk_status"] == sample["risk_status"] and d["calculation_version"] == sample["calculation_version"] and d["risk_score"] is None
    assert Counter(r["risk_status"] for r in db.values()) == Counter(r["risk_status"] for r in rows)
    assert all(r["risk_score"] is None for r in db.values())


@live
def test_latest_risk_selection_is_correct(conn):
    rows = [json.loads(x) for x in (REPO / "data" / "analytics" / "risk" / "gold_operational_risk.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    expected = {}
    for r in rows:
        expected[r["admin_unit_id"]] = max(expected.get(r["admin_unit_id"], ""), r["date"])
    got = {r["admin_unit_id"]: str(r["risk_date"]) for r in q(conn, "SELECT admin_unit_id, risk_date FROM risk.latest_operational_risk")}
    assert got == expected                         # each unit's own maximum date, independent of today's date


@live
def test_map_view_preserves_geometry_risk_relationship(conn):
    m = q(conn, "SELECT * FROM geo.operational_risk_map")
    assert len(m) == len({r["admin_unit_id"] for r in m}) == 76                       # every canonical province/district once
    assert sum(1 for r in m if r["risk_status"] is not None) == q(conn, "SELECT count(*) n FROM risk.latest_operational_risk")[0]["n"]
    no_geom = [r for r in m if r["geometry"] is None]
    assert no_geom and any(r["risk_status"] is not None for r in no_geom)              # risk kept when geometry is NULL
    assert {r["admin_unit_name"] for r in no_geom} >= {"Mangla", "Kamra"}
    for r in m:
        if r["geometry"] is not None:
            assert r["boundary_match_status"] in {"exact", "alias", "manual_verified"}   # only matched boundaries are attached
    matched_ids = {r["pori_admin_unit_id"] for r in q(conn, "SELECT pori_admin_unit_id FROM geo.boundary_crosswalk WHERE pori_admin_unit_id IS NOT NULL")}
    assert {r["admin_unit_id"] for r in m if r["geometry"] is not None} == matched_ids & {r["admin_unit_id"] for r in m}


@live
def test_indexes_exist_for_the_query_patterns(conn):
    names = {r["indexname"] for r in q(conn, "SELECT indexname FROM pg_indexes WHERE schemaname IN ('geo', 'risk')")}
    assert {"ix_operational_risk_date", "ix_operational_risk_status", "ix_operational_risk_province", "ix_boundary_unit_level",
            "ix_boundary_crosswalk_unit"} <= names


@live
def test_quarantine_history_is_intact_and_airflow_is_paused(conn):
    assert q(conn, "SELECT count(*) FILTER (WHERE quarantine_id <= 112) a, count(*) FILTER (WHERE quarantine_id BETWEEN 104 AND 112) b FROM dq.quarantine")[0] == {"a": 112, "b": 9}
    assert all(r["is_paused"] for r in q(conn, "SELECT is_paused FROM dag"))


# ------------------------------------------------------------------ scratch database: rollback + idempotency
def _scratch_ok() -> bool:
    try:
        with engine_for(SCRATCH).connect() as c:
            return bool(c.execute(text("SELECT to_regclass('geo.admin_unit') IS NOT NULL")).scalar_one())
    except Exception:
        return False


@pytest.mark.skipif(not _scratch_ok(), reason="scratch restore database not available")
def test_migration_is_idempotent_and_reversible_on_the_scratch_copy():
    from scripts.geo.load_boundaries import load as load_boundaries
    from scripts.geo.load_boundaries import prepare
    from scripts.risk.load_risk_serving import load as load_risk
    from scripts.risk.load_risk_serving import read_rows
    eng = engine_for(SCRATCH)

    def snapshot():
        with eng.connect() as c:
            admin = c.execute(text("SELECT md5(string_agg(id || name, ',' ORDER BY id)) FROM geo.admin_unit")).scalar_one()
            return admin, c.execute(text("SELECT count(*) FROM geo.name_alias")).scalar_one()

    before = snapshot()
    apply("up", database=SCRATCH)
    apply("up", database=SCRATCH)                                   # rerun = no-op
    assert all(objects_present(eng).values())
    prep = prepare()
    first = load_boundaries(prep, SCRATCH), load_risk(read_rows(), SCRATCH)
    second = load_boundaries(prep, SCRATCH), load_risk(read_rows(), SCRATCH)
    assert first[0] == second[0] and first[1]["current_rows_after_load"] == second[1]["current_rows_after_load"] == len(read_rows())
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM geo.boundary_admin_unit")).scalar_one() == 167      # reruns did not duplicate

    apply("down", database=SCRATCH)                                 # rollback removes only the new objects
    assert not any(objects_present(eng).values())
    assert snapshot() == before                                     # canonical geography untouched
    apply("up", database=SCRATCH)                                   # and the migration can be re-applied
    load_boundaries(prep, SCRATCH)
    load_risk(read_rows(), SCRATCH)
    assert all(objects_present(eng).values()) and snapshot() == before

    with eng.connect() as c:                                        # PostGIS migration is a guarded no-op without PostGIS
        has_postgis = c.execute(text("SELECT count(*) FROM pg_available_extensions WHERE name = 'postgis'")).scalar_one()
    apply("up", with_postgis=True, database=SCRATCH)
    if not has_postgis:
        with eng.connect() as c:
            cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'geo' AND table_name = 'boundary_admin_unit'"))}
        assert "geom" not in cols                                   # nothing half-applied
    _ = hashlib
