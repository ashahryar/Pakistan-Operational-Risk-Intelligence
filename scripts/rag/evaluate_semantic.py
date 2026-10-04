"""Task 30 -- compare lexical (BM25) and semantic retrieval on the evaluation set in config/rag_semantic_eval.yaml.

Runs both retrievers over the REAL stored corpus and embeddings (needs the model weights to embed the queries), prints per-case
precision@k for each, filter compliance, and the top results (verbatim text) for human verification, and writes
data/analytics/rag/semantic_eval_report.json. Nothing is tuned to pass: the report states what happened.

Usage: python scripts/rag/evaluate_semantic.py [--min-score 0.xx] [--database NAME]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from pipeline.rag.embeddings import FastEmbedEmbedder  # noqa: E402
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters, matches, tokenize  # noqa: E402
from pipeline.rag.semantic import DEFAULT_MIN_SCORE, SemanticRetriever  # noqa: E402

CONFIG = PROJECT_ROOT / "config" / "rag_semantic_eval.yaml"
REPORT = PROJECT_ROOT / "data" / "analytics" / "rag" / "semantic_eval_report.json"


def load_eval(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_corpus(database: Optional[str] = None, embedder=None):
    """-> (documents, chunks, embedding rows, embedder) from the stored rag.* tables for the embedder's model/version."""
    from scripts.database.apply_serving_migration import engine_for
    embedder = embedder or FastEmbedEmbedder()
    info = embedder.info
    with engine_for(database).connect() as c:
        q = lambda sql, **p: [dict(r._mapping) for r in c.execute(text(sql), p)]  # noqa: E731
        docs = q("SELECT document_id, source, source_type, title, document_date::text AS document_date, province, admin_unit_id, admin_unit_name, "
                 "provinces, admin_unit_ids, geography_status, geography_basis, event_type, event_types, file_path, url, content_sha256 "
                 "FROM rag.documents WHERE is_current ORDER BY document_id")
        chunks = q("SELECT c.chunk_id, c.document_id, c.chunk_index, c.char_start, c.char_end, c.chunk_text FROM rag.document_chunks c "
                   "JOIN rag.documents d USING (document_id) WHERE c.is_current AND d.is_current ORDER BY c.chunk_id")
        emb = q("SELECT e.chunk_id, e.model_name, e.model_version, e.embedding_dimension, e.embedding FROM rag.chunk_embeddings e "
                "JOIN rag.document_chunks c USING (chunk_id) WHERE e.model_name = :m AND e.model_version = :v AND e.chunk_sha256 = c.chunk_sha256 "
                "ORDER BY e.chunk_id", m=info.name, v=info.version)
    return docs, chunks, emb, embedder


def _filters(case: dict) -> SearchFilters:
    return SearchFilters(**(case.get("filters") or {}))


def _judge(chunk_text: str, terms: list[str]) -> bool:
    low = chunk_text.lower()
    return any(t.lower() in low for t in terms)


def evaluate_case(case: dict, k: int, lex: LexicalRetriever, sem: SemanticRetriever, chunk_by_id: dict, doc_by_id: dict,
                  vocab: set[str], min_score: float) -> dict:
    f = _filters(case)
    out = {"id": case["id"], "category": case["category"], "query": case["query"], "filters": case.get("filters") or {},
           "query_words_absent_from_corpus": [w for w in dict.fromkeys(tokenize(case["query"])) if w not in vocab]}
    for name, hits in (("lexical", lex.search(case["query"], f, k)), ("semantic", sem.search(case["query"], f, k, min_score))):
        rel = [_judge(chunk_by_id[h.chunk_id]["chunk_text"], case["relevant_terms"]) for h in hits] if case["relevant_terms"] else []
        out[name] = {"returned": len(hits), "relevant": sum(rel), "precision_at_k": round(sum(rel) / len(hits), 3) if hits and rel else None,
                     "filters_respected": all(matches(doc_by_id[h.document_id], f) for h in hits),
                     "top": [{"chunk_id": h.chunk_id, "score": h.score, "relevant": r if case["relevant_terms"] else None,
                              "text": " ".join(chunk_by_id[h.chunk_id]["chunk_text"].split())[:170]}
                             for h, r in zip(hits[:3], rel + [None] * 3)]}
    return out


def run(database: Optional[str] = None, min_score: Optional[float] = None, embedder=None) -> dict:
    cfg = load_eval()
    docs, chunks, emb, embedder = load_corpus(database, embedder)
    ms = DEFAULT_MIN_SCORE if min_score is None else min_score
    lex, sem = LexicalRetriever(docs, chunks), SemanticRetriever(docs, chunks, emb, embedder, ms)
    chunk_by_id, doc_by_id = {c["chunk_id"]: c for c in chunks}, {d["document_id"]: d for d in docs}
    vocab = {w for c in chunks for w in tokenize(c["chunk_text"])}
    results = [evaluate_case(c, cfg["k"], lex, sem, chunk_by_id, doc_by_id, vocab, ms) for c in cfg["cases"]]
    para = [r for r in results if r["category"] in ("event_paraphrase", "advisory")]

    def mean(rows, name):
        vals = [r[name]["precision_at_k"] if r[name]["precision_at_k"] is not None else 0.0 for r in rows]
        return round(sum(vals) / len(vals), 3) if vals else None

    summary = {"model": {"name": embedder.info.name, "version": embedder.info.version, "dimension": embedder.info.dimension},
               "min_score": ms, "k": cfg["k"], "chunks": len(chunks), "embedded_chunks": len(emb),
               "paraphrase_mean_precision_at_k": {"lexical": mean(para, "lexical"), "semantic": mean(para, "semantic")},
               "paraphrase_cases_semantic_better": sum((r["semantic"]["precision_at_k"] or 0) > (r["lexical"]["precision_at_k"] or 0) for r in para),
               "paraphrase_cases_lexical_better": sum((r["lexical"]["precision_at_k"] or 0) > (r["semantic"]["precision_at_k"] or 0) for r in para),
               "paraphrase_cases": len(para),
               "filters_respected_everywhere": all(r[n]["filters_respected"] for r in results for n in ("lexical", "semantic")),
               "empty_cases_with_semantic_results": [r["id"] for r in results if r["category"] == "empty" and r["semantic"]["returned"]]}
    return {"summary": summary, "cases": results}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-score", type=float)
    ap.add_argument("--database")
    a = ap.parse_args(argv)
    report = run(a.database, a.min_score)
    print(json.dumps(report["summary"], indent=2))
    for r in report["cases"]:
        print(f"\n[{r['category']}] {r['id']}: {r['query']!r} filters={r['filters']} absent_words={r['query_words_absent_from_corpus']}")
        for n in ("lexical", "semantic"):
            x = r[n]
            print(f"  {n:8} returned={x['returned']} relevant={x['relevant']} p@k={x['precision_at_k']} filters_ok={x['filters_respected']}")
            for t in x["top"][:2]:
                print(f"     {t['score']:<9} rel={t['relevant']!s:5} {t['chunk_id']}  {t['text'][:110]!r}")
    if not a.database and a.min_score is None:
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
