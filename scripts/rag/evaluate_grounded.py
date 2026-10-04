"""Task 31 -- DEVELOPMENT evaluation of the grounded-answer pipeline on the real corpus (config/rag_grounded_eval.yaml).

Always measured (no language model needed):
  * evidence coverage@k: does any of the top-k selected evidence chunks contain an expected term (substring judge), per retrieval mode
  * unsupported questions: how often retrieval itself returns nothing (RETRIEVAL_EMPTY) per mode; otherwise the model must abstain
  * validator probes: for each supported question, deterministic answers built from the REAL retrieved chunk ids are fed to the citation
    validator -- a verbatim excerpt with a correct citation must be ANSWERED; the same with an unknown id, with no citation, and an
    abstention must be INVALID / INVALID / INSUFFICIENT. These probes are NOT model outputs; they test our checks, not a model.
With --live and PORI_LLM_PROVIDER/PORI_LLM_MODEL/PORI_LLM_API_KEY set, the configured provider answers every question and the report adds
status counts, citation validity, abstention on unsupported questions and number warnings. (Not run in this repository's evidence:
no credential was available.)  The report is written to data/analytics/rag/grounded_eval_report.json (offline mode only).

Usage: python scripts/rag/evaluate_grounded.py [--live]
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

from pipeline.rag import grounding as g  # noqa: E402
from pipeline.rag.evidence import build_evidence  # noqa: E402
from pipeline.rag.hybrid import HybridRetriever  # noqa: E402
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters  # noqa: E402
from pipeline.rag.semantic import DEFAULT_MIN_SCORE, SemanticRetriever  # noqa: E402
from scripts.rag.evaluate_semantic import load_corpus  # noqa: E402

CONFIG = PROJECT_ROOT / "config" / "rag_grounded_eval.yaml"
REPORT = PROJECT_ROOT / "data" / "analytics" / "rag" / "grounded_eval_report.json"
MODES = ("lexical", "semantic", "hybrid")


def _excerpt(text: str, n: int = 140) -> str:
    return " ".join(text.split())[:n].rsplit(" ", 1)[0]


def _one_claim(text: str) -> str:
    """First sentence of a chunk excerpt (a single claim, so one trailing citation covers all of it), trailing punctuation removed."""
    import re
    return re.split(r"(?<=[.!?])\s", _excerpt(text, 200))[0].rstrip(".!? ")


def run(live: bool = False, database: Optional[str] = None, embedder=None) -> dict:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    docs, chunks, emb, embedder = load_corpus(database, embedder)
    lex, sem = LexicalRetriever(docs, chunks), SemanticRetriever(docs, chunks, emb, embedder, DEFAULT_MIN_SCORE)
    retrievers = {"lexical": lex, "semantic": sem, "hybrid": HybridRetriever(lex, sem)}
    chunk_by_id, doc_by_id = {c["chunk_id"]: c for c in chunks}, {d["document_id"]: d for d in docs}
    k = cfg["top_k"]

    def retrieve(mode, question, filters):
        f = SearchFilters(**(filters or {}))
        hits = retrievers[mode].search(question, f, k * 3) if mode == "lexical" else retrievers[mode].search(question, f, k * 3, None)
        sel = g.select_evidence(hits, chunk_by_id, k)
        recs = [build_evidence(h, doc_by_id[h.document_id], chunk_by_id[h.chunk_id]) for h in sel]
        return g.pack_evidence(recs, chunk_by_id)

    provider = None
    if live:
        from pipeline.rag.llm import constraints_from_env, provider_from_env
        provider, constraints = provider_from_env(), constraints_from_env()

    out = {"supported": [], "unsupported": []}
    for q in cfg["supported"]:
        row = {"id": q["id"], "question": q["question"], "modes": {}}
        for mode in MODES:
            items = retrieve(mode, q["question"], q.get("filters"))
            covered = any(t in i["text"].lower() for i in items for t in q["expect_terms"])
            first_covering = next((r for r, i in enumerate(items, 1) if any(t in i["text"].lower() for t in q["expect_terms"])), None)
            m = {"evidence": len(items), "covered": covered, "first_covering_rank": first_covering}
            if items:
                top = items[0]
                cid = top["chunk_id"]
                probes = {"valid_citation": g.validate_answer(f"The report states: {_one_claim(top['text'])} [chunk:{cid}].", items).status,
                          "unknown_citation": g.validate_answer(f"The report states: {_one_claim(top['text'])} [chunk:not:retrieved#c0].", items).status,
                          "no_citation": g.validate_answer(f"The report states: {_one_claim(top['text'])}.", items).status,
                          "abstention": g.validate_answer(g.ABSTAIN_TOKEN, items).status}
                m["validator_probes"] = probes
                m["validator_probes_as_expected"] = probes == {"valid_citation": g.ANSWERED, "unknown_citation": g.INVALID,
                                                               "no_citation": g.INVALID, "abstention": g.INSUFFICIENT}
            if provider:
                o = g.answer_question(q["question"], items, provider, constraints)
                m["live"] = {"status": o.status, "citations": o.validation.citations, "problems": o.validation.problems,
                             "warnings": o.validation.warnings, "answer": o.answer}
            row["modes"][mode] = m
        out["supported"].append(row)
    for q in cfg["unsupported"]:
        row = {"id": q["id"], "question": q["question"], "modes": {}}
        for mode in MODES:
            items = retrieve(mode, q["question"], None)
            m = {"evidence": len(items), "retrieval_empty": not items, "top": [_excerpt(i["text"], 90) for i in items[:2]]}
            if provider and items:
                o = g.answer_question(q["question"], items, provider, constraints)
                m["live"] = {"status": o.status, "answer": o.answer}
            row["modes"][mode] = m
        out["unsupported"].append(row)

    sup, uns = out["supported"], out["unsupported"]
    summary = {"top_k": k, "supported_questions": len(sup), "unsupported_questions": len(uns), "live_model": bool(provider),
               "evidence_coverage_at_k": {m: sum(r["modes"][m]["covered"] for r in sup) for m in MODES},
               "unsupported_with_empty_retrieval": {m: sum(r["modes"][m]["retrieval_empty"] for r in uns) for m in MODES},
               "unsupported_evidence_chunks_returned": {m: sum(r["modes"][m]["evidence"] for r in uns) for m in MODES},
               "validator_probes_as_expected": {m: f"{sum(r['modes'][m].get('validator_probes_as_expected', False) for r in sup)}/{sum('validator_probes' in r['modes'][m] for r in sup)}"
                                                for m in MODES}}
    if provider:
        def live(rows, mode):
            return [r["modes"][mode]["live"] for r in rows if "live" in r["modes"][mode]]
        summary["live"] = {m: {"supported_status": {s: sum(x["status"] == s for x in live(sup, m)) for s in {x["status"] for x in live(sup, m)}},
                               "supported_invalid_answers": sum(x["status"] == g.INVALID for x in live(sup, m)),
                               "supported_number_warnings": sum(len(x["warnings"]) for x in live(sup, m)),
                               "unsupported_abstained_or_empty": sum(r["modes"][m]["retrieval_empty"] or r["modes"][m].get("live", {}).get("status") == g.INSUFFICIENT for r in uns),
                               "unsupported_answered": [r["id"] for r in uns if r["modes"][m].get("live", {}).get("status") == g.ANSWERED]} for m in MODES}
    return {"summary": summary, **out}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="also ask the configured LLM provider (needs PORI_LLM_* in the environment)")
    a = ap.parse_args(argv)
    report = run(a.live)
    print(json.dumps(report["summary"], indent=2))
    for r in report["supported"]:
        print(f"[supported] {r['id']}: " + "  ".join(f"{m}: cov={r['modes'][m]['covered']} rank={r['modes'][m]['first_covering_rank']}" for m in MODES))
    for r in report["unsupported"]:
        print(f"[unsupported] {r['id']}: " + "  ".join(f"{m}: n={r['modes'][m]['evidence']}" for m in MODES))
    if not a.live:
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
