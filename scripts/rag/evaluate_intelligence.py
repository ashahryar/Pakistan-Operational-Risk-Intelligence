"""Task 32 -- DEVELOPMENT evaluation of GET /api/v1/intelligence/ask on the real local data (config/rag_intelligence_eval.yaml).

Measured without a language model (the API answers 503 LLM_UNAVAILABLE but still returns the risk context and the evidence):
  * risk-context selection: the returned record must equal an INDEPENDENT SQL read of the risk tables for the expected unit (or be absent when
    none should exist: ambiguous place, no row on the asked date -- a different date must never be substituted)
  * documentary evidence: do the retrieved chunks contain an expected term (substring judge)
  * unsupported questions: no risk context, and how many junk chunks retrieval still returns
  * provenance probes: deterministic answers built from the REAL returned risk record and chunks are fed to the validator -- a correctly separated
    answer must be ANSWERED; a fabricated causal link, a wrong status, a mixed-provenance sentence and an unknown citation must be INVALID_ANSWER.
    These probes are NOT model output: they test our checks, not whether a real model avoids false causality.
With --live and PORI_LLM_PROVIDER/PORI_LLM_MODEL/PORI_LLM_API_KEY set, the configured provider is used and the status of every answer is recorded
(not run in this repository's evidence: no credential was available). Report: data/analytics/rag/intelligence_eval_report.json (offline mode only).

Usage: python scripts/rag/evaluate_intelligence.py [--live]
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

from pipeline.intelligence.grounding import validate_intelligence_answer  # noqa: E402

CONFIG = PROJECT_ROOT / "config" / "rag_intelligence_eval.yaml"
REPORT = PROJECT_ROOT / "data" / "analytics" / "rag" / "intelligence_eval_report.json"


def independent_risk(conn, unit_name: str, risk_date: Optional[str]) -> Optional[dict]:
    """Direct SQL read (a different code path from the API service) of the expected risk row."""
    if risk_date:
        sql = ("SELECT admin_unit_id, risk_date::text AS risk_date, risk_status, risk_confidence, data_coverage_pct::float AS cov, calculation_version "
               "FROM risk.operational_risk r JOIN geo.admin_unit u ON u.id = r.admin_unit_id WHERE r.is_current AND u.name = :n AND r.risk_date = :d")
        row = conn.execute(text(sql), {"n": unit_name, "d": risk_date}).fetchone()
    else:
        sql = ("SELECT admin_unit_id, risk_date::text AS risk_date, risk_status, risk_confidence, data_coverage_pct::float AS cov, calculation_version "
               "FROM risk.latest_operational_risk WHERE admin_unit_name = :n")
        row = conn.execute(text(sql), {"n": unit_name}).fetchone()
    return dict(row._mapping) if row else None


def probes(body: dict) -> Optional[dict]:
    rec = body["risk_context"]["record"]
    docs = body["documentary_evidence"]
    if not rec or not docs:
        return None
    items = [{"chunk_id": e["chunk_id"], "text": e["snippet"]} for e in docs]
    cid = items[0]["chunk_id"]
    first = " ".join(items[0]["text"].split())
    claim = first.split(". ")[0][:140].rstrip(". ")
    good = (f"The risk engine classifies {rec['admin_unit_name']} as {rec['risk_status']} with {rec['risk_confidence']} confidence [risk_engine]. "
            f"One retrieved report states: {claim} [chunk:{cid}].")
    wrong = "HIGH" if rec["risk_status"] != "HIGH" else "LOW"
    cases = {"separated_answer": (good, "ANSWERED"),
             "causal_link_fabricated": (f"The risk engine classifies {rec['admin_unit_name']} as {rec['risk_status']} because NDMA reported flooding [risk_engine].", "INVALID_ANSWER"),
             "wrong_status": (f"The risk engine classifies {rec['admin_unit_name']} as {wrong} [risk_engine].", "INVALID_ANSWER"),
             "mixed_provenance": (f"{rec['admin_unit_name']} is {rec['risk_status']} [risk_engine] and a report describes it [chunk:{cid}].", "INVALID_ANSWER"),
             "unknown_citation": ("A report states that events occurred nearby [chunk:not:retrieved#c0].", "INVALID_ANSWER"),
             "document_claims_risk_status": (f"A retrieved report classified the operational risk as severe [chunk:{cid}].", "INVALID_ANSWER")}
    got = {k: validate_intelligence_answer(t, items, rec).status for k, (t, _) in cases.items()}
    return {"statuses": got, "as_expected": all(got[k] == exp for k, (_, exp) in cases.items())}


def run(live: bool = False, embedder=None) -> dict:
    from fastapi.testclient import TestClient

    import api.app.services.rag as svc
    from api.app.main import app
    from pipeline.rag.embeddings import FastEmbedEmbedder
    from scripts.database.apply_serving_migration import engine_for

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    svc.set_embedder(embedder or FastEmbedEmbedder())
    svc.set_llm_provider(None)                                    # offline: environment configuration only (none) unless --live
    client, rows = TestClient(app), []
    try:
        with engine_for(None).connect() as conn:
            for c in cfg["cases"]:
                params = {"q": c["question"], "top_k": cfg["top_k"]}
                if c.get("source"):
                    params["source"] = c["source"]
                body = client.get("/api/v1/intelligence/ask", params=params).json()
                rec, ctxd = body["risk_context"]["record"], body["question_context"]
                row = {"id": c["id"], "kind": c["kind"], "question": c["question"], "status": body["status"], "geography_status": ctxd["geography_status"],
                       "unit": (ctxd["admin_unit"] or {}).get("name"), "risk_status": rec["risk_status"] if rec else None,
                       "risk_date": rec["risk_date"] if rec else None, "risk_reason": body["risk_context"]["reason"],
                       "evidence": len(body["documentary_evidence"]), "filters_applied": body["retrieval"]["filters_applied"],
                       "filters_relaxed": body["retrieval"]["filters_relaxed"],
                       "top_evidence": [" ".join(e["snippet"].split())[:100] for e in body["documentary_evidence"][:2]]}
                if c["kind"] in ("risk", "mixed"):
                    if "expect_unit" in c and c["expect_unit"] is None:
                        row["risk_context_correct"] = rec is None and body["status"] == c.get("expect_status", "NO_RISK_CONTEXT")
                    else:
                        truth = independent_risk(conn, c["expect_unit"], c.get("expect_risk_date"))
                        if c.get("expect_no_record"):
                            truth_latest = independent_risk(conn, c["expect_unit"], None)
                            row["risk_context_correct"] = rec is None and truth is None and (truth_latest is not None) and "no risk record exists" in (row["risk_reason"] or "")
                        else:
                            row["risk_context_correct"] = bool(truth and rec and rec["admin_unit_id"] == truth["admin_unit_id"] and rec["risk_date"] == truth["risk_date"]
                                                               and rec["risk_status"] == truth["risk_status"] and rec["risk_confidence"] == truth["risk_confidence"]
                                                               and rec["calculation_version"] == truth["calculation_version"] and rec["risk_score"] is None)
                if c["kind"] in ("documentary", "mixed"):
                    row["evidence_has_expected_term"] = any(t in e["snippet"].lower() for e in body["documentary_evidence"] for t in c["expect_terms"])
                if c["kind"] == "unsupported":
                    row["unsupported_handled"] = rec is None and body["status"] in ("NO_RISK_CONTEXT", "RETRIEVAL_EMPTY", "LLM_UNAVAILABLE")
                    row["junk_chunks_returned"] = len(body["documentary_evidence"])
                p = probes(body)
                if p:
                    row["provenance_probes"] = p
                if live:
                    row["live_status"] = body["status"]
                    row["live_problems"] = body["groundedness"]["problems"]
                rows.append(row)
    finally:
        svc.set_embedder(None)
    risk = [r for r in rows if "risk_context_correct" in r]
    docs = [r for r in rows if "evidence_has_expected_term" in r]
    uns = [r for r in rows if r["kind"] == "unsupported"]
    pr = [r for r in rows if "provenance_probes" in r]
    summary = {"live_model": live, "cases": len(rows),
               "risk_context_selection_correct": f"{sum(r['risk_context_correct'] for r in risk)}/{len(risk)}",
               "documentary_evidence_has_expected_term": f"{sum(r['evidence_has_expected_term'] for r in docs)}/{len(docs)}",
               "unsupported_without_risk_context": f"{sum(r['unsupported_handled'] for r in uns)}/{len(uns)}",
               "unsupported_junk_chunks_returned": {r["id"]: r["junk_chunks_returned"] for r in uns},
               "provenance_probe_cases": len(pr), "provenance_probes_as_expected": f"{sum(r['provenance_probes']['as_expected'] for r in pr)}/{len(pr)}",
               "status_counts": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
               "note": "No language model was run: explanation quality, citation behaviour and causal-claim behaviour of a real model are not measured." if not live else "live provider used"}
    return {"summary": summary, "cases": rows}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="use the provider configured by PORI_LLM_* instead of the offline path")
    a = ap.parse_args(argv)
    report = run(a.live)
    print(json.dumps(report["summary"], indent=2))
    for r in report["cases"]:
        flags = {k: r[k] for k in ("risk_context_correct", "evidence_has_expected_term", "unsupported_handled") if k in r}
        print(f"[{r['kind']}] {r['id']}: status={r['status']} unit={r['unit']} risk={r['risk_status']}@{r['risk_date']} docs={r['evidence']} relaxed={r['filters_relaxed']} {flags}")
    if not a.live:
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
