"""Task 33 -- database tests for the ml.* prediction storage. Static SQL checks always run; live checks run against the loaded local tables; the
rollback / idempotency test runs against the scratch database `pori_t33_restore_check` (a restored copy of the pre-migration backup) so the live
database is never rolled back; it is skipped if that scratch database is absent."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts.database.apply_ml_migration import apply, tables_present
from scripts.database.apply_serving_migration import engine_for

REPO = Path(__file__).resolve().parents[2]
UP = (REPO / "db" / "migrations" / "0033_ml_predictions.up.sql").read_text(encoding="utf-8")
DOWN = (REPO / "db" / "migrations" / "0033_ml_predictions.down.sql").read_text(encoding="utf-8")
SCRATCH = "pori_t33_restore_check"


def sql_only(s: str) -> str:
    return "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("--"))


# ------------------------------------------------------------------ static
def test_up_migration_is_additive_and_confined_to_the_ml_schema():
    body = sql_only(UP)
    assert not re.search(r"\b(DROP|TRUNCATE|DELETE|UPDATE)\b", body, re.I) and not re.search(r"ALTER\s+TABLE", body, re.I)
    created = re.findall(r"CREATE TABLE IF NOT EXISTS ([\w.]+)", body)
    assert created == ["ml.model_runs", "ml.predictions"] and "CREATE SCHEMA IF NOT EXISTS ml" in body
    assert re.findall(r"REFERENCES ([\w.]+)", body) == ["ml.model_runs", "geo.admin_unit"]
    for forbidden in ("risk.", "rag.", "dq.", "public."):
        assert forbidden not in body.replace("risk_", "")


def test_contract_checks_are_in_the_schema():
    body = sql_only(UP)
    assert "CHECK ((status = 'INSUFFICIENT_DATA') = (prediction IS NULL))" in body and "CHECK (feature_cutoff < prediction_date)" in body
    assert "'PREDICTED', 'BASELINE_ONLY', 'INSUFFICIENT_DATA'" in body and "PRIMARY KEY (model_run_id, entity_id, horizon_days)" in body
    assert "risk_score" not in body and "risk_status" not in body


def test_down_migration_removes_only_ml_objects():
    body = sql_only(DOWN)
    assert re.findall(r"DROP (?:TABLE|SCHEMA) IF EXISTS ([\w.]+)", body) == ["ml.predictions", "ml.model_runs", "ml"]
    assert "CASCADE" not in body.upper()


# ------------------------------------------------------------------ live
@pytest.fixture(scope="module")
def conn():
    try:
        c = engine_for().connect()
        c.execute(text("SELECT 1"))
        if not all(tables_present().values()):
            pytest.skip("ml.* tables not present")
    except Exception:
        pytest.skip("database not reachable")
    yield c
    c.close()


def test_live_contract_holds_for_every_stored_row(conn):
    n_bad = conn.execute(text("SELECT count(*) FROM ml.predictions WHERE (status = 'INSUFFICIENT_DATA') <> (prediction IS NULL) OR feature_cutoff >= prediction_date")).scalar_one()
    assert n_bad == 0
    assert conn.execute(text("SELECT count(*) FROM ml.predictions WHERE provenance->>'provenance' <> 'ML_MODEL'")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM ml.predictions p LEFT JOIN geo.admin_unit u ON u.id = p.admin_unit_id WHERE u.id IS NULL AND p.admin_unit_id IS NOT NULL")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM ml.predictions WHERE status = 'PREDICTED' AND model_type <> 'ml'")).scalar_one() == 0


def test_live_one_current_row_per_unit_and_horizon(conn):
    dup = conn.execute(text("SELECT count(*) FROM (SELECT admin_unit_id, horizon_days, target FROM ml.predictions WHERE is_current GROUP BY 1, 2, 3 HAVING count(*) > 1) d")).scalar_one()
    assert dup == 0


def test_existing_tables_are_unchanged_by_the_ml_layer(conn):
    assert conn.execute(text("SELECT count(*) FROM dq.quarantine")).scalar_one() == 158
    assert conn.execute(text("SELECT count(*) FROM risk.operational_risk")).scalar_one() == 1586
    assert conn.execute(text("SELECT count(*) FROM risk.operational_risk WHERE risk_score IS NOT NULL")).scalar_one() == 0


# ------------------------------------------------------------------ scratch: idempotency, versioning, rollback
def _scratch_ok() -> bool:
    try:
        with engine_for(SCRATCH).connect() as c:
            return bool(c.execute(text("SELECT to_regclass('geo.admin_unit') IS NOT NULL")).scalar_one())
    except Exception:
        return False


@pytest.mark.skipif(not _scratch_ok(), reason=f"scratch database {SCRATCH} not available")
def test_load_is_idempotent_versioned_and_reversible_on_the_scratch_copy():
    pytest.importorskip("sklearn")
    import numpy as np
    import pandas as pd

    from pipeline.ml.runner import TargetSpec, run_target
    from scripts.ml.run_prediction_pipeline import upsert

    eng = engine_for(SCRATCH)
    spec = TargetSpec("air_quality_index", "air_quality", "AQI", "admin_unit_id", "date", "aqi_avg", "synthetic scratch test")
    with eng.connect() as c:
        units = [dict(r._mapping) for r in c.execute(text("SELECT id, level, name FROM geo.admin_unit WHERE level IN (1, 2) ORDER BY id LIMIT 6"))]

    def make(seed):
        rng = np.random.default_rng(seed)
        d0 = pd.Timestamp("2025-01-01")
        return [{"admin_unit_id": units[0]["id"], "date": (d0 + pd.Timedelta(days=i)).date().isoformat(), "aqi_avg": float(100 + 30 * np.sin(2 * np.pi * i / 7) + rng.normal(0, 1))}
                for i in range(260)]

    def hash_units():
        with eng.connect() as c:
            return c.execute(text("SELECT md5(string_agg(id || name, ',' ORDER BY id)) FROM geo.admin_unit")).scalar_one()

    before = hash_units()
    apply("down", SCRATCH)
    apply("up", SCRATCH)
    apply("up", SCRATCH)                                                                      # rerun = no-op
    r1 = run_target(make(1), spec, units, horizons=(1, 3))
    first, second = upsert(r1, SCRATCH), upsert(r1, SCRATCH)
    assert first == second == {"runs": 2, "predictions": 2 * len(units)}
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ml.predictions")).scalar_one() == 2 * len(units)                  # no duplicates after the second load
        assert c.execute(text("SELECT count(*) FROM ml.predictions WHERE status = 'INSUFFICIENT_DATA'")).scalar_one() == 2 * (len(units) - 1)
        assert c.execute(text("SELECT count(*) FROM ml.model_runs WHERE is_current")).scalar_one() == 2
    r2 = run_target(make(2), spec, units, horizons=(1, 3))                                  # new data -> new version; the old one stops being current
    assert r2["fingerprint"] != r1["fingerprint"]
    upsert(r2, SCRATCH)
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM ml.model_runs WHERE is_current")).scalar_one() == 2
        assert c.execute(text("SELECT count(*) FROM ml.model_runs")).scalar_one() == 4
        assert c.execute(text("SELECT count(*) FROM ml.predictions WHERE is_current")).scalar_one() == 2 * len(units)
    apply("down", SCRATCH)
    assert not any(tables_present(SCRATCH).values()) and hash_units() == before
    apply("up", SCRATCH)                                                                      # leave the scratch copy migrated
    assert all(tables_present(SCRATCH).values())
