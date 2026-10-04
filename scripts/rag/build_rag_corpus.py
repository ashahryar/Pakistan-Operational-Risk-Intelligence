"""Task 29 -- build the RAG corpus from the existing parsed document artifacts and (optionally) load it into rag.*.

Reads (read-only): data/parsed/{ndma,pdma,pmd,canonical}. Writes artifacts to data/analytics/rag/ (documents.jsonl and
chunks.jsonl are gitignored and regenerable; summary + skipped report are tracked) and, with --load, upserts rag.documents /
rag.document_chunks (rows absent from this build are flagged is_current = FALSE, never deleted). Deterministic: running it
twice yields byte-identical artifacts and identical ids.

Usage: python scripts/rag/build_rag_corpus.py [--load] [--database NAME]
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

from pipeline.rag.index import build_corpus  # noqa: E402

OUT = PROJECT_ROOT / "data" / "analytics" / "rag"
JSON_COLS = ("provinces", "districts", "admin_unit_ids", "geography_text", "event_types", "event_type_raw", "metadata")
DOC_COLS = ["document_id", "source", "source_type", "title", "document_date", "document_date_text", "document_date_basis", "published_at",
            "url", "file_path", "province", "admin_unit_id", "admin_unit_name", "provinces", "districts", "admin_unit_ids",
            "geography_status", "geography_basis", "geography_text", "event_type", "event_types", "event_type_raw", "language_script",
            "raw_text", "content_sha256", "metadata", "ingestion_timestamp", "parser_version", "normalization_version"]
CHUNK_COLS = ["chunk_id", "document_id", "chunk_index", "char_start", "char_end", "chunk_text", "chunk_sha256", "chunker_version"]


def unit_lookup(database: Optional[str] = None) -> dict[str, int]:
    """Canonical province/district name -> geo.admin_unit id (read-only). Empty if the database is unreachable."""
    try:
        from scripts.database.apply_serving_migration import engine_for
        with engine_for(database).connect() as conn:
            rows = conn.execute(text("SELECT name, id FROM geo.admin_unit WHERE level IN (1, 2) ORDER BY id")).fetchall()
    except Exception:
        return {}
    out: dict[str, int] = {}
    for name, uid in rows:
        out.setdefault(name, uid)
    return out


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def write_artifacts(corpus: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _jsonl(OUT / "documents.jsonl", corpus["documents"])
    _jsonl(OUT / "chunks.jsonl", corpus["chunks"])
    report = {**corpus["summary"], "discovered_by_reader": corpus["discovered_by_reader"],
              "skipped": corpus["skipped"], "non_document_artifacts": corpus["non_document_artifacts"]}
    (OUT / "rag_corpus_summary.json").write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def load(corpus: dict, database: Optional[str] = None) -> dict:
    from scripts.database.apply_serving_migration import engine_for
    dmarks = ", ".join(f"CAST(:{c} AS jsonb)" if c in JSON_COLS else (f"CAST(:{c} AS date)" if c == "document_date" else f":{c}") for c in DOC_COLS)
    dsql = text(f"INSERT INTO rag.documents ({', '.join(DOC_COLS)}, is_current) VALUES ({dmarks}, TRUE) ON CONFLICT (document_id) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in DOC_COLS if c != "document_id") + ", is_current = TRUE, loaded_at = now()")
    csql = text(f"INSERT INTO rag.document_chunks ({', '.join(CHUNK_COLS)}, is_current) VALUES ({', '.join(':' + c for c in CHUNK_COLS)}, TRUE) "
                "ON CONFLICT (chunk_id) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in CHUNK_COLS if c != "chunk_id") + ", is_current = TRUE")
    docs = [{**d, **{k: json.dumps(d[k], ensure_ascii=False, sort_keys=True) for k in JSON_COLS}} for d in corpus["documents"]]
    with engine_for(database).begin() as conn:
        conn.execute(text("UPDATE rag.document_chunks SET is_current = FALSE WHERE is_current"))
        conn.execute(text("UPDATE rag.documents SET is_current = FALSE WHERE is_current"))
        for i in range(0, len(docs), 100):
            conn.execute(dsql, docs[i:i + 100])
        for i in range(0, len(corpus["chunks"]), 500):
            conn.execute(csql, corpus["chunks"][i:i + 500])
        nd = conn.execute(text("SELECT count(*) FROM rag.documents WHERE is_current")).scalar_one()
        nc = conn.execute(text("SELECT count(*) FROM rag.document_chunks WHERE is_current")).scalar_one()
    return {"documents_current": nd, "chunks_current": nc}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--load", action="store_true", help="also upsert into rag.documents / rag.document_chunks")
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    lookup = unit_lookup(a.database)
    corpus = build_corpus(PROJECT_ROOT, lookup)
    write_artifacts(corpus)
    print(json.dumps({**corpus["summary"], "admin_unit_lookup_entries": len(lookup), "skipped": len(corpus["skipped"])}, indent=2))
    if a.load:
        print(json.dumps(load(corpus, a.database), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
