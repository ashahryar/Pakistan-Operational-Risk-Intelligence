"""Risk context block: the existing risk-engine record, carried unchanged and labelled RISK_ENGINE.

Nothing here calculates, adjusts or interprets risk. `record` is exactly the shape served by api/app/services/risk_serving.py
(`risk_score` stays null in engine v1.0.0). When no record exists the block says NO_RISK_CONTEXT and why; a record is never invented,
and a different date is never silently substituted for the one asked for.
"""

from __future__ import annotations

from typing import Optional

AVAILABLE = "AVAILABLE"
NO_RISK_CONTEXT = "NO_RISK_CONTEXT"
PROVENANCE = "RISK_ENGINE"
CITATION_TAG = "[risk_engine]"

BLOCK_NOTE = ("Computed by the operational risk engine from its own input signals. This is not documentary evidence, and documents "
              "retrieved separately are NOT inputs to this classification.")


def risk_context_block(record: Optional[dict], reason: Optional[str], lookup: dict) -> dict:
    if record is None:
        return {"status": NO_RISK_CONTEXT, "provenance": PROVENANCE, "record": None, "reason": reason or "no risk record found", "lookup": lookup,
                "note": BLOCK_NOTE}
    return {"status": AVAILABLE, "provenance": PROVENANCE, "record": record, "reason": None, "lookup": lookup, "note": BLOCK_NOTE}


def risk_prompt_item(block: dict) -> Optional[dict]:
    """The item handed to the language model for the engine part (None when there is no risk context)."""
    if block["status"] != AVAILABLE:
        return None
    return {"kind": "risk_engine", "record": block["record"], "lookup": block["lookup"]}


def engine_values_text(record: dict) -> str:
    """Every value of the engine record as text (used to check that numbers quoted from the engine exist in it)."""
    parts = []
    for k, v in record.items():
        if isinstance(v, dict):
            parts.extend(f"{k}.{kk}={vv}" for kk, vv in v.items())
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)
