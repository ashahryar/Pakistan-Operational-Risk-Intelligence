"""Task 30 -- generate REAL embeddings for the current RAG chunks and store them in rag.chunk_embeddings.

Backend/pipeline operation (never part of an API request). Reads rag.document_chunks (is_current), embeds every chunk that has no
stored vector for this exact (model_name, model_version) -- or whose stored vector was computed from different chunk text -- and
upserts one row per (chunk_id, model_name, model_version). Re-running with nothing changed embeds nothing and creates no rows.
Other models' embeddings are never touched. A chunk that cannot be embedded is reported as failed; no placeholder is stored.

Usage: python scripts/rag/embed_chunks.py [--database NAME] [--batch-size 32] [--limit N] [--dry-run]
Requires: pip install -r requirements/embeddings.txt (model weights are fetched once, pinned to an immutable revision).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from pipeline.rag.embeddings import FastEmbedEmbedder, build_embedding_records  # noqa: E402

OUT = PROJECT_ROOT / "data" / "analytics" / "rag" / "embedding_run_summary.json"
UPSERT = text("""
    INSERT INTO rag.chunk_embeddings (chunk_id, model_name, model_version, embedding_dimension, embedding, normalized, chunk_sha256, metadata)
    VALUES (:chunk_id, :model_name, :model_version, :embedding_dimension, CAST(:embedding AS real[]), :normalized, :chunk_sha256,
            CAST(:metadata AS jsonb))
    ON CONFLICT (chunk_id, model_name, model_version) DO UPDATE SET
        embedding = EXCLUDED.embedding, embedding_dimension = EXCLUDED.embedding_dimension, normalized = EXCLUDED.normalized,
        chunk_sha256 = EXCLUDED.chunk_sha256, metadata = EXCLUDED.metadata, created_at = now()
    WHERE rag.chunk_embeddings.chunk_sha256 <> EXCLUDED.chunk_sha256""")


def pending_chunks(conn, model_name: str, model_version: str) -> tuple[list[dict], int, int]:
    """-> (chunks needing a vector, total current chunks, already embedded and up to date)."""
    rows = [dict(r._mapping) for r in conn.execute(text(
        "SELECT c.chunk_id, c.chunk_text, c.chunk_sha256, e.chunk_sha256 AS embedded_sha256 "
        "FROM rag.document_chunks c JOIN rag.documents d USING (document_id) "
        "LEFT JOIN rag.chunk_embeddings e ON e.chunk_id = c.chunk_id AND e.model_name = :m AND e.model_version = :v "
        "WHERE c.is_current AND d.is_current ORDER BY c.chunk_id"), {"m": model_name, "v": model_version})]
    todo = [r for r in rows if r["embedded_sha256"] != r["chunk_sha256"]]
    return todo, len(rows), len(rows) - len(todo)


def repair_metadata(database: Optional[str] = None, embedder=None) -> int:
    """Fill run metadata on stored rows of this exact model/version that have none (rows written before metadata was captured).
    Vectors are not touched or recomputed. Returns the number of rows updated."""
    from scripts.database.apply_serving_migration import engine_for
    embedder = embedder or FastEmbedEmbedder()
    embedder.embed_documents(["metadata probe"])            # loads a lazy model so info.metadata is populated
    meta = json.dumps(embedder.info.metadata, sort_keys=True)
    with engine_for(database).begin() as conn:
        return conn.execute(text("UPDATE rag.chunk_embeddings SET metadata = CAST(:m AS jsonb) WHERE model_name = :n AND model_version = :v "
                                 "AND metadata = CAST('{}' AS jsonb)"), {"m": meta, "n": embedder.info.name, "v": embedder.info.version}).rowcount


def run(database: Optional[str] = None, batch_size: int = 32, limit: Optional[int] = None, dry_run: bool = False,
        embedder=None) -> dict:
    from scripts.database.apply_serving_migration import engine_for
    embedder = embedder or FastEmbedEmbedder()
    eng = engine_for(database)
    t0 = time.time()
    with eng.connect() as conn:
        todo, total, done = pending_chunks(conn, embedder.info.name, embedder.info.version)
    if limit:
        todo = todo[:limit]
    report = {"model_name": embedder.info.name, "model_version": embedder.info.version, "embedding_dimension": embedder.info.dimension,
              "chunks_current": total, "already_embedded": done, "to_embed": len(todo), "embedded_now": 0, "failed": [], "dry_run": dry_run}
    if dry_run or not todo:
        report["embedding_metadata"] = embedder.info.metadata
        return report
    records, failures = build_embedding_records(todo, embedder, batch_size)
    with eng.begin() as conn:
        for i in range(0, len(records), 200):
            conn.execute(UPSERT, [{**r, "embedding": r["embedding"], "metadata": json.dumps(r["metadata"], sort_keys=True)}
                                  for r in records[i:i + 200]])
        stored = conn.execute(text("SELECT count(*) FROM rag.chunk_embeddings WHERE model_name = :m AND model_version = :v"),
                              {"m": embedder.info.name, "v": embedder.info.version}).scalar_one()
    report.update(embedded_now=len(records), failed=failures, stored_for_model=stored, seconds=round(time.time() - t0, 1),
                  embedding_metadata=embedder.info.metadata)
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--database")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repair-metadata", action="store_true", help="only fill empty run metadata on stored rows; no re-embedding")
    a = ap.parse_args(argv)
    if a.repair_metadata:
        print(json.dumps({"rows_repaired": repair_metadata(a.database)}))
        return 0
    report = run(a.database, a.batch_size, a.limit, a.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not a.dry_run and not a.database and not a.limit:
        OUT.write_text(json.dumps({k: v for k, v in report.items() if k != "seconds"}, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
