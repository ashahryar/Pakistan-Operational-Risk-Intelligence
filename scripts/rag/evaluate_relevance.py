"""Task 35 -- evaluate and SELECT the RAG relevance / abstention policy (pipeline/rag/relevance.py) on the frozen set config/rag_relevance_eval.yaml.

For every case and retrieval mode (BM25 lexical, semantic, hybrid RRF) the top-5 results are recorded UNGATED with their signals (query-word coverage, share of query
words absent from the corpus, embedding cosine), judged relevant or not, and then classified by a candidate policy.

Protocol (three iterations, all reported in docs/architecture/RAG_RELEVANCE_STATUS.md; this script runs the last one):
  iteration 1  coverage / cosine thresholds selected on `dev`, reported on `holdout`: unsupported false positives stayed high (0.36 lexical, 0.43 hybrid).
  iteration 2  `holdout` had been seen, so it joined the selection pool; reported on the fresh `holdout2`.
  iteration 3  the EXISTING Task 32 real-data test showed the policy lost question-form evidence (8/8 -> 3/8): keyword-style cases under-represented real
               questions. The Task 32 questions joined the pool, `holdout2` (seen) joined it too, a fresh question-form `holdout3` was written before any of its scores
               existed, and a question-framing stop-word list was added to the relevance signal. The final policy is reported ONLY on `holdout3`.
Selection rule (fixed in advance, deterministic): over a grid of thresholds choose the policy that maximises the BALANCED ACCURACY of the query-level decision on the
selection pool (1 - (false-abstention rate on supported queries + false-positive rate on unsupported/difficult-negative queries) / 2) subject to an EVIDENCE LOSS <= 0.15
(supported queries whose ungated top-5 had a relevant chunk but whose gated list has none: the loss the gate itself causes; queries the retriever already missed are
not charged to the gate; the cap was first drafted as 0.10 and raised to 0.15 after viewing the dev frontier, before any holdout result existed); ties -> higher
precision@5 of the gated lists on supported queries, then smaller (less restrictive) thresholds.

  python scripts/rag/evaluate_relevance.py --select    selection on the pool only; holdout3 is not shown
  python scripts/rag/evaluate_relevance.py             full report with the policy currently in pipeline/rag/relevance.py; writes
                                                       data/analytics/rag/relevance_eval_report.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.rag import relevance as R  # noqa: E402
from pipeline.rag.hybrid import HybridRetriever  # noqa: E402
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters, matches  # noqa: E402
from pipeline.rag.semantic import DEFAULT_MIN_SCORE, SemanticRetriever  # noqa: E402
from scripts.rag.evaluate_semantic import _judge, load_corpus  # noqa: E402

CONFIG = PROJECT_ROOT / "config" / "rag_relevance_eval.yaml"
REPORT = PROJECT_ROOT / "data" / "analytics" / "rag" / "relevance_eval_report.json"
MODES = ("lexical", "semantic", "hybrid")
K = 5
MAX_EVIDENCE_LOSS = 0.15
POOL_SPLITS = ("dev", "holdout", "holdout2")


def load_cases(path: Path = CONFIG) -> tuple[list[dict], dict]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    base = yaml.safe_load((path.parent / cfg["include"]).read_text(encoding="utf-8"))
    cases = list(base["cases"]) + list(cfg["cases"])
    seen: set = set()
    for c in cases:
        if c["id"] in seen:
            raise ValueError(f"duplicate case id {c['id']}")
        seen.add(c["id"])
        c["group"] = ("supported" if c.get("relevant_terms") else "difficult_negative" if c["category"] == "difficult_negative" else "unsupported")
    counters: dict = {}
    for c in cases:                                              # alternate within each group, in file order: dev, holdout, dev, ... (an explicit `split` wins)
        if c.get("split"):
            continue
        n = counters.get(c["group"], 0)
        c["split"] = "dev" if n % 2 == 0 else "holdout"
        counters[c["group"]] = n + 1
    return cases, cfg


def validate_case(c: dict, chunks: list[dict], docs_by_id: dict) -> Optional[str]:
    low = [x["chunk_text"].lower() for x in chunks]
    for t in c.get("absent_terms") or []:
        if any(t.lower() in x for x in low):
            return f"absent term {t!r} occurs in the corpus"
    if c["group"] == "supported":
        f = SearchFilters(**(c.get("filters") or {}))
        n = sum(1 for ch, x in zip(chunks, low) if matches(docs_by_id[ch["document_id"]], f) and any(t.lower() in x for t in c["relevant_terms"]))
        if n == 0:
            return "no chunk in the corpus (under the filters) contains a relevant term"
    return None


def collect(cases, lex, sem, hyb, chunks, docs_by_id) -> list[dict]:
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    out = []
    for c in cases:
        why = validate_case(c, chunks, docs_by_id)
        row = {"id": c["id"], "category": c["category"], "group": c["group"], "split": c["split"], "query": c["query"], "filters": c.get("filters") or {}, "invalid": why}
        if why:
            out.append(row)
            continue
        f = SearchFilters(**(c.get("filters") or {}))
        terms = c.get("relevant_terms") or []
        if terms:
            row["relevant_in_corpus"] = sum(1 for ch in chunks if matches(docs_by_id[ch["document_id"]], f) and _judge(ch["chunk_text"], terms))
        for mode, hits in (("lexical", lex.search(c["query"], f, K)), ("semantic", sem.search(c["query"], f, K, DEFAULT_MIN_SCORE)),
                           ("hybrid", hyb.search(c["query"], f, K, DEFAULT_MIN_SCORE))):
            ass = R.assess_hits(mode, c["query"], hits, lex, sem.cosines) if hits else []
            for h, a in zip(hits, ass):
                a["relevant"] = _judge(chunk_by_id[h.chunk_id]["chunk_text"], terms) if terms else None
                a["score"] = h.score
                a["text"] = " ".join(chunk_by_id[h.chunk_id]["chunk_text"].split())[:110]
            row[mode] = ass
        out.append(row)
    return out


# ------------------------------------------------------------------------------------------------------------------------------ metrics
def decide(mode: str, ass: list[dict], policy: Optional[dict]) -> tuple[list[dict], bool]:
    """The gated list (None policy = ungated: every returned chunk is treated as evidence) and whether the query is answered."""
    if policy is None:
        return ass, bool(ass)
    kept = [a for a in ass if R.chunk_passes(mode, a["coverage"], a["cosine"], {mode: policy}, a["absent_share"])]
    return kept, bool(kept)


def metrics(rows: list[dict], mode: str, policy: Optional[dict]) -> dict:
    sup = [r for r in rows if r["group"] == "supported" and not r["invalid"]]
    neg = [r for r in rows if r["group"] != "supported" and not r["invalid"]]
    diff = [r for r in neg if r["group"] == "difficult_negative"]
    p5, rec, succ, false_abst, lost = [], [], 0, 0, 0
    for r in sup:
        kept, answered = decide(mode, r[mode], policy)
        rel = sum(1 for a in kept if a["relevant"])
        p5.append(rel / len(kept) if kept else 0.0)
        rec.append(rel / min(K, r["relevant_in_corpus"]))
        succ += rel > 0
        false_abst += not answered
        lost += (any(a["relevant"] for a in r[mode]) and rel == 0)
    fp = sum(decide(mode, r[mode], policy)[1] for r in neg)
    fpd = sum(decide(mode, r[mode], policy)[1] for r in diff)
    n_s, n_n = len(sup), len(neg)
    correct = (n_s - false_abst) + (n_n - fp)
    return {"supported_cases": n_s, "unsupported_cases": n_n, "difficult_negative_cases": len(diff),
            "supported_precision_at_5": round(sum(p5) / n_s, 3) if n_s else None, "supported_recall_at_5": round(sum(rec) / n_s, 3) if n_s else None,
            "supported_success_at_5": f"{succ}/{n_s}", "false_abstention_rate": round(false_abst / n_s, 3) if n_s else None, "false_abstentions": f"{false_abst}/{n_s}",
            "evidence_lost_vs_ungated": f"{lost}/{n_s}", "evidence_loss_rate": round(lost / n_s, 3) if n_s else 0.0,
            "unsupported_false_positive_rate": round(fp / n_n, 3) if n_n else None, "unsupported_false_positives": f"{fp}/{n_n}",
            "difficult_negative_false_positives": f"{fpd}/{len(diff)}",
            "abstention_accuracy": round(correct / (n_s + n_n), 3) if (n_s + n_n) else None,
            "balanced_accuracy": round(1 - ((false_abst / n_s if n_s else 0) + (fp / n_n if n_n else 0)) / 2, 3)}


# ------------------------------------------------------------------------------------------------------------------------------ selection
def grid(mode: str) -> list[dict]:
    cov = [round(0.05 * i, 2) for i in range(0, 21)]
    absent = [round(0.1 * i, 1) for i in range(0, 11)]
    cos = [round(0.60 + 0.01 * i, 2) for i in range(0, 31)]
    if mode == "lexical":
        return [{"min_coverage": c, "max_absent_share": a} for c, a in itertools.product(cov, absent)]
    if mode == "semantic":
        return [{"min_cosine": s} for s in [round(0.50 + 0.01 * i, 2) for i in range(0, 41)]]
    out = [{"min_coverage": c, "max_absent_share": a, "rule": "or"} for c, a in itertools.product(cov, absent)] + [{"min_cosine": s, "rule": "or"} for s in cos]
    for c, a, s, rule in itertools.product(cov, absent, cos, ("or", "and")):
        out.append({"min_coverage": c, "max_absent_share": a, "min_cosine": s, "rule": rule})
    return out


def select(rows: list[dict], mode: str) -> tuple[dict, dict, int]:
    pool = [r for r in rows if r["split"] in POOL_SPLITS]
    best, best_key, evaluated = None, None, 0
    for pol in grid(mode):
        m = metrics(pool, mode, pol)
        evaluated += 1
        if m["evidence_loss_rate"] > MAX_EVIDENCE_LOSS:
            continue
        thr = sum(v for k, v in pol.items() if k in ("min_coverage", "min_cosine")) + sum(1 - v for k, v in pol.items() if k == "max_absent_share")
        key = (-m["balanced_accuracy"], -m["supported_precision_at_5"], round(thr, 6), json.dumps(pol, sort_keys=True))
        if best_key is None or key < best_key:
            best, best_key = pol, key
    if best is None:
        raise RuntimeError(f"no {mode} policy keeps the pool evidence loss <= {MAX_EVIDENCE_LOSS}")
    return best, metrics(pool, mode, best), evaluated


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--select", action="store_true", help="select thresholds on the pool (dev + holdout) and print pool metrics only (holdout3 not shown)")
    a = ap.parse_args(argv)
    cases, cfg = load_cases()
    docs, chunks, emb, embedder = load_corpus()
    lex = LexicalRetriever(docs, chunks)
    sem = SemanticRetriever(docs, chunks, emb, embedder, DEFAULT_MIN_SCORE)
    hyb = HybridRetriever(lex, sem)
    rows = collect(cases, lex, sem, hyb, chunks, {d["document_id"]: d for d in docs})
    invalid = [{"id": r["id"], "why": r["invalid"]} for r in rows if r["invalid"]]
    splits = ("dev", "holdout", "holdout2", "holdout3")
    group_counts = {g: {s: sum(1 for r in rows if r["group"] == g and r["split"] == s and not r["invalid"]) for s in splits} for g in ("supported", "unsupported", "difficult_negative")}
    selected, pool_metrics, evaluated = {}, {}, {}
    for mode in MODES:
        selected[mode], pool_metrics[mode], evaluated[mode] = select(rows, mode)
    print("cases per group/split:", json.dumps(group_counts), "| invalid cases:", invalid)
    for mode in MODES:
        print(f"selected[{mode}] = {json.dumps(selected[mode])}  ({evaluated[mode]} candidates)\n   pool metrics: {json.dumps(pool_metrics[mode])}")
    if a.select:
        print("\n(--select: holdout3 deliberately not shown)")
        return 0
    module_policy = {m: R.POLICY[m] for m in MODES}
    equals = module_policy == selected
    report = {"cases": len(rows), "invalid_cases": invalid, "group_counts": group_counts, "protocol": __doc__.split("Protocol")[1].split("  python")[0].strip(),
              "selection": {"pool_splits": list(POOL_SPLITS), "max_evidence_loss": MAX_EVIDENCE_LOSS, "selected": selected, "candidates_evaluated": evaluated,
                            "pool_metrics_selected": pool_metrics}, "module_policy": module_policy, "module_policy_equals_selection": equals,
              "policy_version": R.POLICY_VERSION, "metrics": {}, "cases_detail": rows}
    for name, picks in (("dev", ("dev",)), ("holdout_iteration1", ("holdout",)), ("holdout2_iteration2", ("holdout2",)), ("pool_selection", POOL_SPLITS), ("holdout3_final", ("holdout3",)), ("all", splits)):
        sub = [r for r in rows if r["split"] in picks]
        report["metrics"][name] = {m: {"before_ungated": metrics(sub, m, None), "after_gated": metrics(sub, m, R.POLICY[m])} for m in MODES}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"\nmodule POLICY equals the deterministic selection: {equals}")
    for name in report["metrics"]:
        print(f"\n=== {name} ===")
        print(f"{'mode':9} {'variant':8} {'sup P@5':>8} {'sup R@5':>8} {'unsup FPR':>10} {'diff-neg FP':>12} {'abst.acc':>9} {'false-abst':>11} {'lost':>6}")
        for m in MODES:
            for v, key in (("before", "before_ungated"), ("after", "after_gated")):
                x = report["metrics"][name][m][key]
                print(f"{m:9} {v:8} {x['supported_precision_at_5']:>8} {x['supported_recall_at_5']:>8} {x['unsupported_false_positive_rate']:>10} "
                      f"{x['difficult_negative_false_positives']:>12} {x['abstention_accuracy']:>9} {x['false_abstentions']:>11} {x['evidence_lost_vs_ungated']:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
