"""Task 34 -- response assembly: turns tool results into the separate, provenance-labelled blocks of the agent response.

Blocks stay separate end to end (as in the intelligence layer): `risk_context` (RISK_ENGINE), `documentary_evidence` (RAG_DOCUMENT), `ml_prediction`
(ML_MODEL for a validated model, BASELINE_MODEL for a baseline) and `geography` (GEOGRAPHY). Nothing is merged, interpreted or recomputed here. A baseline
forecast always carries the label "BASELINE_ONLY — NOT VALIDATED ML".
"""

from __future__ import annotations

from typing import Optional

from pipeline.agents import contracts as C
from pipeline.intelligence import risk_context as rc

VALID_ML = ("PREDICTED", "BASELINE_ONLY")


def attribution(row: dict) -> str:
    """BASELINE_MODEL for a baseline forecast, ML_MODEL only for a validated ML model."""
    return C.BASELINE_MODEL if (row.get("model_type") == "baseline" or row.get("status") == "BASELINE_ONLY") else C.ML_MODEL


def label_row(row: dict) -> dict:
    out = dict(row)
    out["attribution"] = attribution(row)
    out["label"] = C.BASELINE_LABEL if row.get("status") == "BASELINE_ONLY" else ("PREDICTED — validated ML model" if row.get("status") == "PREDICTED" else "INSUFFICIENT_DATA")
    return out


def ml_components(result: Optional[dict], requested_target: Optional[str] = None) -> tuple[Optional[dict], dict]:
    """-> (ml_prediction block or None, component status). Rows are never relabelled: a BASELINE_ONLY row is never presented as PREDICTED."""
    if result is None:
        return None, {"status": "NOT_REQUESTED"}
    rows = result.get("predictions") or []
    valid = [label_row(r) for r in rows if r.get("status") in VALID_ML and r.get("prediction") is not None]
    insufficient = [r for r in rows if r.get("status") == "INSUFFICIENT_DATA"]
    if not valid:
        if result.get("unsupported_target"):
            reason = (f"no ML model exists for the requested target '{result['unsupported_target']}'. "
                      f"Available targets: {', '.join(result.get('targets') or []) or 'none'}. No forecast was substituted.")
        elif result.get("horizon_requested") and not rows:
            reason = (f"no prediction exists for a horizon of {result['horizon_requested']} day(s) "
                      f"(available horizons: {', '.join(str(h) for h in result.get('available_horizons') or []) or 'none'}).")
        elif insufficient:
            reason = insufficient[0].get("reason") or "the ML layer reports INSUFFICIENT_DATA for this area"
        else:
            reason = "the ML layer holds no prediction row for this area"
        return None, {"status": "INSUFFICIENT_DATA", "reason": reason, "insufficient_rows": insufficient}
    block = rc.ml_prediction_block(valid)
    block["attributions"] = sorted({r["attribution"] for r in valid})
    block["baseline_label"] = C.BASELINE_LABEL if any(r["status"] == "BASELINE_ONLY" for r in valid) else None
    status = "PREDICTED" if any(r["status"] == "PREDICTED" for r in valid) else "BASELINE_ONLY"
    return block, {"status": status, "attributions": block["attributions"], "validated_against_baseline": block["validated_against_baseline"], "insufficient_rows": insufficient}


def citations_for(records: list, cited_chunk_ids, answer: Optional[str], record: Optional[dict], ml_block: Optional[dict]) -> list:
    """Citations of an ANSWERED response (the same shapes as the intelligence layer, plus the model attribution for ML)."""
    out = [{"kind": "documentary", "chunk_id": e["chunk_id"], "document_id": e["document_id"], "title": e["title"], "source": e["source"],
            "document_date": e["document_date"], "source_reference": e["source_reference"], "provenance": C.RAG_DOCUMENT}
           for e in records if e["chunk_id"] in set(cited_chunk_ids)]
    if answer and rc.CITATION_TAG in answer and record:
        out.append({"kind": "risk_engine", "admin_unit_id": record["admin_unit_id"], "risk_date": record["risk_date"],
                    "calculation_version": record["calculation_version"], "provenance": C.RISK_ENGINE})
    if answer and rc.ML_CITATION_TAG in answer and ml_block:
        out.append({"kind": "ml_prediction", "model_run_ids": sorted({p["model_run_id"] for p in ml_block["predictions"]}),
                    "attributions": ml_block["attributions"], "provenance": "+".join(ml_block["attributions"])})
    return out


def provenance_block(*, geography: Optional[dict], risk_block: Optional[dict], records: list, ml_block: Optional[dict], tool_trace: list) -> dict:
    rec = (risk_block or {}).get("record")
    return {
        "geography": {"source": C.GEOGRAPHY, "available": bool(geography and geography.get("unit")), "admin_unit_id": (geography or {}).get("unit", {}).get("id") if geography and geography.get("unit") else None},
        "risk_context": {"source": C.RISK_ENGINE, "available": rec is not None, "calculation_version": rec["calculation_version"] if rec else None,
                         "risk_date": rec["risk_date"] if rec else None},
        "documentary_evidence": {"source": C.RAG_DOCUMENT, "chunk_ids": [e["chunk_id"] for e in records], "document_ids": sorted({e["document_id"] for e in records})},
        "ml_prediction": {"sources": (ml_block or {}).get("attributions", []), "available": ml_block is not None,
                          "model_run_ids": sorted({p["model_run_id"] for p in ml_block["predictions"]}) if ml_block else []},
        "tools": [{"tool_name": t["tool_name"], "status": t["status"], "sources": t["provenance"].get("sources", [])} for t in tool_trace],
        "note": "Each block keeps the provenance of the capability that produced it. A document never becomes a risk-engine input, an ML or baseline forecast is "
                "never a current risk status, and a BASELINE_MODEL forecast is never described as a validated ML model."}
