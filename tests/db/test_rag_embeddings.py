"""Task 30 -- database tests for rag.chunk_embeddings.

Static SQL checks always run. Live checks run against the real stored embeddings once they exist. The idempotency / model-version /
staleness / rollback tests run against the scratch copy `pori_t30_restore_check` using the TEST-ONLY stand-in embedder (the
production path is `embed_chunks.run`, exercised here with a stand-in so it does not need the model); they skip if the scratch
database is absent."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts.database.apply_rag_migration import apply, tables_present
from scripts.database.apply_serving_migration import engine_for
from tests.rag.test_embeddings_unit import DIM, ConceptStandIn

REPO = Path(__file__).resolve().parents[2]
UP = (REPO / "db" / "migrations" / "0030_rag_chunk_embeddings.up.sql").read_text(encoding="utf-8")
DOWN = (REPO / "db" / "migrations" / "0030_rag_chunk_embeddings.down.sql").read_text(encoding="utf-8")
SCRATCH = "pori_t30_restore_check"
CODE = re.sub(r"--[^\n]*", "", UP)


# ------------------------------------------------------------------ static
def test_migration_is_additive_and_idempotent():
    up = CODE.upper()
    for forbidden in ("DROP ", "TRUNCATE", "DELETE ", "ALTER TABLE", "UPDATE ", "INSERT "):
        assert forbidden not in up, forbidden
    assert re.findall(r"CREATE (?:UNIQUE )?(?:TABLE|SCHEMA|INDEX)(?! IF NOT EXISTS)", CODE) == []
    assert "REFERENCES rag.document_chunks(chunk_id)" in CODE and CODE.count("REFERENCES") == 1
    for existing in ("risk.", "geo.", "dq.", "quarantine"):
        assert existing not in CODE


def test_schema_identifies_chunk_model_version_and_dimension_and_allows_several_models():
    assert "PRIMARY KEY (chunk_id, model_name, model_version)" in CODE            # one vector per chunk per model/version; models coexist
    for col in ("chunk_id", "model_name", "model_version", "embedding_dimension", "embedding", "chunk_sha256", "created_at", "normalized"):
        assert re.search(rf"\b{col}\b", CODE), col
    assert "CHECK (cardinality(embedding) = embedding_dimension)" in CODE           # stored dimension must match the vector
    assert "REAL[]" in CODE and "vector(" not in CODE.lower() and "CREATE EXTENSION" not in CODE.upper()   # no pgvector assumed


def test_rollback_removes_only_the_embeddings_table():
    code = re.sub(r"--[^\n]*", "", DOWN)
    assert re.findall(r"DROP TABLE IF EXISTS ([\w.]+)", code) == ["rag.chunk_embeddings"]
    assert "CASCADE" not in code.upper() and "rag.documents" not in code and "rag.document_chunks" not in code


# ------------------------------------------------------------------ live (real embeddings)
def _live() -> bool:
    try:
        with engine_for().connect() as c:
            return bool(c.execute(text("SELECT to_regclass('rag.chunk_embeddings') IS NOT NULL AND (SELECT count(*) FROM rag.chunk_embeddings) > 0")).scalar_one())
    except Exception:
        return False


live = pytest.mark.skipif(not _live(), reason="no stored embeddings")


@pytest.fixture(scope="module")
def conn():
    with engine_for().connect() as c:
        yield c


def q(conn, sql, **p):
    return [dict(r._mapping) for r in conn.execute(text(sql), p)]


@live
def test_every_current_chunk_has_exactly_one_real_embedding_for_the_model(conn):
    r = q(conn, "SELECT count(*) n, count(DISTINCT chunk_id) d, count(DISTINCT (model_name, model_version)) m FROM rag.chunk_embeddings")[0]
    assert r == {"n": 1909, "d": 1909, "m": 1}
    assert q(conn, "SELECT DISTINCT model_name, model_version, embedding_dimension FROM rag.chunk_embeddings") == [
        {"model_name": "BAAI/bge-small-en-v1.5", "model_version": "hf:Qdrant/bge-small-en-v1.5-onnx-Q@aa8f8b060edb00e03bfdd08813a2949946c8ba55",
         "embedding_dimension": 384}]
    assert not q(conn, "SELECT 1 FROM rag.document_chunks c JOIN rag.documents d USING (document_id) LEFT JOIN rag.chunk_embeddings e USING (chunk_id) "
                       "WHERE c.is_current AND d.is_current AND e.chunk_id IS NULL")
    assert not q(conn, "SELECT 1 FROM rag.chunk_embeddings e JOIN rag.document_chunks c USING (chunk_id) WHERE e.chunk_sha256 <> c.chunk_sha256")  # none stale


@live
def test_stored_vectors_are_valid_unit_vectors_with_run_metadata(conn):
    assert not q(conn, "SELECT 1 FROM rag.chunk_embeddings WHERE cardinality(embedding) <> 384 OR embedding_dimension <> 384 OR NOT normalized")
    for r in q(conn, "SELECT chunk_id, embedding FROM rag.chunk_embeddings ORDER BY chunk_id LIMIT 60"):
        norm = math.sqrt(sum(x * x for x in r["embedding"]))
        assert abs(norm - 1.0) < 1e-3 and all(math.isfinite(x) for x in r["embedding"]) and any(abs(x) > 1e-6 for x in r["embedding"])
    meta = q(conn, "SELECT DISTINCT metadata FROM rag.chunk_embeddings")
    assert len(meta) == 1 and meta[0]["metadata"]["library"] == "fastembed" and meta[0]["metadata"]["hf_revision"] == "aa8f8b060edb00e03bfdd08813a2949946c8ba55"
    assert meta[0]["metadata"]["weights_sha256"] and meta[0]["metadata"]["quantized"] is True


@live
def test_vectors_are_not_placeholders(conn):
    rows = q(conn, "SELECT chunk_sha256, embedding FROM rag.chunk_embeddings")
    vectors, texts = {tuple(r["embedding"]) for r in rows}, {r["chunk_sha256"] for r in rows}
    assert len(vectors) == len(texts) > 1000                    # one distinct vector per distinct chunk text: identical vectors only ever
    by_vec: dict = {}                                            # come from identical text (repeated report boilerplate), never a constant fill
    for r in rows:
        by_vec.setdefault(tuple(r["embedding"]), set()).add(r["chunk_sha256"])
    assert all(len(s) == 1 for s in by_vec.values())
    assert max(max(r["embedding"]) for r in rows) < 1.0 and min(min(r["embedding"]) for r in rows) > -1.0


@live
def test_existing_data_is_untouched(conn):
    assert q(conn, "SELECT count(*) n FROM rag.documents WHERE is_current")[0]["n"] == 253 and q(conn, "SELECT count(*) n FROM rag.document_chunks WHERE is_current")[0]["n"] == 1909
    assert {r["level"]: r["n"] for r in q(conn, "SELECT level, count(*) n FROM geo.admin_unit GROUP BY 1")} == {0: 1, 1: 7, 2: 69}
    assert q(conn, "SELECT count(*) FILTER (WHERE quarantine_id <= 112) a, count(*) FILTER (WHERE quarantine_id BETWEEN 104 AND 112) b FROM dq.quarantine")[0] == {"a": 112, "b": 9}
    assert not q(conn, "SELECT 1 FROM pg_extension WHERE extname IN ('postgis', 'vector')")


@live
def test_rerunning_the_generator_embeds_nothing_and_creates_no_rows():
    from scripts.rag.embed_chunks import run

    class NeverCalled(ConceptStandIn):
        pass
    from pipeline.rag.embeddings import FastEmbedEmbedder
    report = run(dry_run=True, embedder=FastEmbedEmbedder())                           # dry run: no model is loaded
    assert report["to_embed"] == 0 and report["already_embedded"] == report["chunks_current"] == 1909 and report["failed"] == []
    _ = NeverCalled


# ------------------------------------------------------------------ scratch: idempotency, versions, staleness, rollback
def _vectors(eng) -> list:
    with eng.connect() as c:
        return [tuple(r) for r in c.execute(text("SELECT chunk_id, embedding::text FROM rag.chunk_embeddings WHERE model_version = 'v1' ORDER BY chunk_id"))]


def _scratch_ok() -> bool:
    try:
        with engine_for(SCRATCH).connect() as c:
            return bool(c.execute(text("SELECT to_regclass('rag.document_chunks') IS NOT NULL")).scalar_one())
    except Exception:
        return False


@pytest.mark.skipif(not _scratch_ok(), reason="scratch restore database not available")
def test_generation_is_idempotent_versioned_stale_aware_and_reversible_on_the_scratch_copy():
    from scripts.rag.embed_chunks import repair_metadata, run
    eng = engine_for(SCRATCH)
    apply("down", SCRATCH, embeddings=True)
    apply("up", SCRATCH, embeddings=True)
    apply("up", SCRATCH, embeddings=True)                                              # migration rerun = no-op
    with eng.connect() as c:
        chunks = c.execute(text("SELECT count(*) FROM rag.document_chunks WHERE is_current")).scalar_one()
    assert chunks > 100

    first = run(SCRATCH, embedder=ConceptStandIn())
    assert first["to_embed"] == chunks and first["embedded_now"] == chunks and first["failed"] == [] and first["stored_for_model"] == chunks
    again = run(SCRATCH, embedder=ConceptStandIn())                                    # same chunk ids + model + version
    assert again["to_embed"] == 0 and again["embedded_now"] == 0 and again["already_embedded"] == chunks

    with eng.connect() as c:
        assert c.execute(text("SELECT count(*), count(DISTINCT chunk_id) FROM rag.chunk_embeddings")).fetchone() == (chunks, chunks)
        assert c.execute(text("SELECT count(DISTINCT embedding_dimension), min(embedding_dimension) FROM rag.chunk_embeddings")).fetchone() == (1, DIM)

    other = run(SCRATCH, embedder=ConceptStandIn("stand-in", "v2"))                    # a new version coexists, nothing is overwritten
    assert other["embedded_now"] == chunks
    with eng.connect() as c:
        assert {tuple(r) for r in c.execute(text("SELECT model_version, count(*) FROM rag.chunk_embeddings GROUP BY 1"))} == {("v1", chunks), ("v2", chunks)}

    with eng.begin() as c:                                                             # simulate a changed chunk: its vector is stale
        victim = c.execute(text("SELECT chunk_id FROM rag.document_chunks WHERE is_current ORDER BY chunk_id LIMIT 1")).scalar_one()
        c.execute(text("UPDATE rag.document_chunks SET chunk_sha256 = 'changed' WHERE chunk_id = :c"), {"c": victim})
    stale = run(SCRATCH, embedder=ConceptStandIn())
    assert stale["to_embed"] == 1 and stale["embedded_now"] == 1
    with eng.connect() as c:
        assert c.execute(text("SELECT chunk_sha256 FROM rag.chunk_embeddings WHERE chunk_id = :c AND model_version = 'v1'"), {"c": victim}).scalar_one() == "changed"
        assert c.execute(text("SELECT count(*) FROM rag.chunk_embeddings WHERE model_version = 'v1'")).scalar_one() == chunks         # replaced, not duplicated

    with eng.begin() as c:                                                             # restore the scratch chunk
        real = c.execute(text("SELECT chunk_sha256 FROM rag.chunk_embeddings WHERE model_version = 'v2' AND chunk_id = :c"), {"c": victim}).scalar_one()
        c.execute(text("UPDATE rag.document_chunks SET chunk_sha256 = :s WHERE chunk_id = :c"), {"s": real, "c": victim})

    with eng.begin() as c:                                                             # rows written without run metadata can be repaired in place
        c.execute(text("UPDATE rag.chunk_embeddings SET metadata = CAST('{}' AS jsonb) WHERE model_version = 'v1'"))
    before_vec = _vectors(eng)
    assert repair_metadata(SCRATCH, ConceptStandIn()) == chunks and repair_metadata(SCRATCH, ConceptStandIn()) == 0     # idempotent
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM rag.chunk_embeddings WHERE model_version = 'v1' AND metadata = CAST('{\"test_only\": true}' AS jsonb)")).scalar_one() == chunks
    assert _vectors(eng) == before_vec                                                 # repair never touches or recomputes vectors

    dry = run(SCRATCH, embedder=ConceptStandIn(), dry_run=True)
    assert dry["dry_run"] is True and dry["embedded_now"] == 0

    apply("down", SCRATCH, embeddings=True)                                            # rollback removes only the embeddings table
    t = tables_present(SCRATCH)
    assert t["rag.chunk_embeddings"] is False and t["rag.documents"] and t["rag.document_chunks"]
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM rag.document_chunks WHERE is_current")).scalar_one() == chunks
    apply("up", SCRATCH, embeddings=True)
    _ = json
