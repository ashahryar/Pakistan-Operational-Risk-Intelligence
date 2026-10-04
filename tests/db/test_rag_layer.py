"""Task 29 -- database tests for the rag.* storage layer.

Static SQL checks always run. Live checks run against the loaded local tables. The rollback / idempotency test runs against
the scratch database `pori_t29_restore_check` (a restored copy of the pre-Task-29 backup) so the live database is never
rolled back; it is skipped if that scratch database is absent."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts.database.apply_rag_migration import apply, tables_present
from scripts.database.apply_serving_migration import engine_for

REPO = Path(__file__).resolve().parents[2]
UP = (REPO / "db" / "migrations" / "0029_rag_foundation.up.sql").read_text(encoding="utf-8")
DOWN = (REPO / "db" / "migrations" / "0029_rag_foundation.down.sql").read_text(encoding="utf-8")
SCRATCH = "pori_t29_restore_check"


# ------------------------------------------------------------------ static
def test_migration_is_additive_and_touches_nothing_existing():
    code = re.sub(r"--[^\n]*", "", UP)
    up = code.upper()
    for forbidden in ("DROP ", "TRUNCATE", "DELETE ", "ALTER TABLE", "UPDATE ", "INSERT "):
        assert forbidden not in up, forbidden
    assert re.findall(r"CREATE (?:UNIQUE )?(?:TABLE|SCHEMA|INDEX)(?! IF NOT EXISTS)", code) == []          # every CREATE is idempotent
    assert len(re.findall(r"CREATE (?:UNIQUE )?(?:TABLE|SCHEMA|INDEX) IF NOT EXISTS", code)) >= 8
    for existing in ("risk.", "dq.", "geo.name_alias", "quarantine"):
        assert existing not in code
    assert "geo.admin_unit" in code and code.count("REFERENCES geo.admin_unit(id)") == 1          # read-only foreign key


def test_no_vector_column_is_faked():
    code = re.sub(r"--[^\n]*", "", UP).lower()
    assert "vector" not in code and "embedding" not in code


def test_rollback_removes_only_rag_objects():
    assert set(re.findall(r"DROP TABLE IF EXISTS ([\w.]+)", DOWN)) == {"rag.document_chunks", "rag.documents"}
    assert "CASCADE" not in DOWN.upper() and "geo." not in re.sub(r"--[^\n]*", "", DOWN) and "quarantine" not in DOWN.lower()


# ------------------------------------------------------------------ live
def _live() -> bool:
    try:
        with engine_for().connect() as c:
            return bool(c.execute(text("SELECT to_regclass('rag.documents') IS NOT NULL AND (SELECT count(*) FROM rag.documents) > 0")).scalar_one())
    except Exception:
        return False


live = pytest.mark.skipif(not _live(), reason="rag tables not loaded")


@pytest.fixture(scope="module")
def conn():
    with engine_for().connect() as c:
        yield c


def q(conn, sql, **p):
    return [dict(r._mapping) for r in conn.execute(text(sql), p)]


@live
def test_counts_and_uniqueness(conn):
    assert q(conn, "SELECT count(*) n, count(DISTINCT document_id) d FROM rag.documents WHERE is_current")[0] == {"n": 253, "d": 253}
    assert q(conn, "SELECT count(*) n, count(DISTINCT chunk_id) d FROM rag.document_chunks WHERE is_current")[0] == {"n": 1909, "d": 1909}
    assert not q(conn, "SELECT 1 FROM rag.document_chunks c LEFT JOIN rag.documents d USING (document_id) WHERE d.document_id IS NULL")
    assert not q(conn, "SELECT 1 FROM rag.document_chunks WHERE chunk_id NOT LIKE document_id || '#c%'")                 # every chunk names its document


@live
def test_text_is_stored_verbatim_and_chunks_are_exact_slices(conn):
    for r in q(conn, "SELECT document_id, raw_text, content_sha256 FROM rag.documents WHERE is_current ORDER BY document_id LIMIT 40"):
        assert hashlib.sha256(r["raw_text"].encode("utf-8")).hexdigest() == r["content_sha256"]
    bad = q(conn, "SELECT c.chunk_id FROM rag.document_chunks c JOIN rag.documents d USING (document_id) "
                  "WHERE substr(d.raw_text, c.char_start + 1, c.char_end - c.char_start) <> c.chunk_text LIMIT 5")
    assert bad == []


@live
def test_provenance_geography_and_dates_are_honest(conn):
    assert not q(conn, "SELECT 1 FROM rag.documents WHERE document_date IS NOT NULL AND document_date_basis <> 'report_date'")
    assert q(conn, "SELECT count(*) n FROM rag.documents WHERE document_date IS NULL")[0]["n"] > 0           # missing dates stay missing
    assert not q(conn, "SELECT 1 FROM rag.documents WHERE source IN ('ffc', 'pmd_ndmc') AND (province IS NOT NULL OR admin_unit_id IS NOT NULL)")
    assert not q(conn, "SELECT 1 FROM rag.documents WHERE geography_status = 'unresolved' AND (province IS NOT NULL OR admin_unit_id IS NOT NULL)")
    assert not q(conn, "SELECT 1 FROM rag.documents WHERE file_path IS NULL OR content_sha256 IS NULL OR normalization_version IS NULL")
    assert not q(conn, "SELECT 1 FROM rag.documents WHERE admin_unit_id IS NOT NULL AND admin_unit_id NOT IN (SELECT id FROM geo.admin_unit)")
    assert not q(conn, "SELECT 1 FROM rag.documents WHERE source = 'ffc' AND url NOT LIKE 'https://ffc.gov.pk/%'")           # urls only where the source has one


@live
def test_existing_data_is_untouched(conn):
    assert {r["level"]: r["n"] for r in q(conn, "SELECT level, count(*) n FROM geo.admin_unit GROUP BY 1")} == {0: 1, 1: 7, 2: 69}
    assert q(conn, "SELECT count(*) n FROM risk.operational_risk WHERE is_current")[0]["n"] == 1586
    assert q(conn, "SELECT count(*) FILTER (WHERE quarantine_id <= 112) a, count(*) FILTER (WHERE quarantine_id BETWEEN 104 AND 112) b FROM dq.quarantine")[0] == {"a": 112, "b": 9}
    assert all(r["is_paused"] for r in q(conn, "SELECT is_paused FROM dag"))
    assert not q(conn, "SELECT 1 FROM pg_extension WHERE extname IN ('postgis', 'vector')")


# ------------------------------------------------------------------ scratch: rollback + idempotency
def _scratch_ok() -> bool:
    try:
        with engine_for(SCRATCH).connect() as c:
            return bool(c.execute(text("SELECT to_regclass('geo.admin_unit') IS NOT NULL")).scalar_one())
    except Exception:
        return False


@pytest.mark.skipif(not _scratch_ok(), reason="scratch restore database not available")
def test_migration_is_idempotent_and_reversible_on_the_scratch_copy():
    from scripts.rag.build_rag_corpus import load, unit_lookup
    from pipeline.rag.index import build_corpus
    eng = engine_for(SCRATCH)

    def admin_hash():
        with eng.connect() as c:
            return c.execute(text("SELECT md5(string_agg(id || name, ',' ORDER BY id)) FROM geo.admin_unit")).scalar_one()

    before = admin_hash()
    apply("up", SCRATCH)
    apply("up", SCRATCH)                                           # rerun = no-op
    assert all(tables_present(SCRATCH).values())
    corpus = build_corpus(REPO, unit_lookup(SCRATCH))
    first, second = load(corpus, SCRATCH), load(corpus, SCRATCH)
    assert first == second == {"documents_current": len(corpus["documents"]), "chunks_current": len(corpus["chunks"])}      # no duplicates
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM rag.document_chunks")).scalar_one() == len(corpus["chunks"])
    apply("down", SCRATCH)
    assert not any(tables_present(SCRATCH).values()) and admin_hash() == before
    apply("up", SCRATCH)
    load(corpus, SCRATCH)
    assert all(tables_present(SCRATCH).values()) and admin_hash() == before
