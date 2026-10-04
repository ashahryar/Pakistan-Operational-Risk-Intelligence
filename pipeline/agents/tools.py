"""Task 34 -- the CLOSED allowlist of agent tools and their strict typed contracts.

Every tool is read-only and maps onto an existing trusted capability. There is deliberately NO tool that executes SQL, touches the file system, runs a
command, or requests an arbitrary URL: such a call cannot even be expressed, because an unknown tool name is rejected (`unknown_tool`) before anything
runs. Arguments are validated against the declared specification (`validate_call`): unknown arguments, missing required arguments, wrong types, values out
of range, malformed dates and enum violations are all rejected as INVALID_TOOL_CALL; free-text arguments are additionally scanned for SQL / URLs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from pipeline.agents import contracts as C
from pipeline.agents.policy import scan_free_text

MAX_TEXT = 300
RETRIEVAL_MODES = ("lexical", "semantic", "hybrid")
SOURCES = ("ndma", "pdma", "pmd", "pmd_ndmc", "ffc")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class Arg:
    kind: str                                  # int | str | date | enum | bool
    required: bool = False
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    choices: tuple = ()
    free_text: bool = False                    # a natural-language string (scanned for SQL / URLs); other strings must be short identifiers
    description: str = ""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: dict
    provenance: tuple                          # the provenance values this tool can produce
    read_only: bool = True


def _specs() -> dict[str, ToolSpec]:
    uid = Arg("int", minimum=1, description="canonical geo.admin_unit id (province or district)")
    s = [
        ToolSpec("geography.resolve_place", "Resolve the place named in a text to a canonical province/district (exact, alias or normalised matches only; never fuzzy; "
                 "an ambiguous name returns its candidate interpretations).",
                 {"text": Arg("str", required=True, free_text=True, description="text containing a place name")}, (C.GEOGRAPHY,)),
        ToolSpec("geography.get_admin_unit", "Canonical information about one province/district (name, level, parent province, boundary availability).",
                 {"admin_unit_id": Arg("int", required=True, minimum=1)}, (C.GEOGRAPHY,)),
        ToolSpec("geography.list_units", "List canonical provinces/districts, optionally for one province.",
                 {"level": Arg("int", minimum=1, maximum=2), "province": Arg("str", description="canonical province name"), "limit": Arg("int", minimum=1, maximum=200)}, (C.GEOGRAPHY,)),
        ToolSpec("risk.latest", "The latest risk-engine record of one area (the area's own most recent date, not today's date).",
                 {"admin_unit_id": Arg("int", required=True, minimum=1)}, (C.RISK_ENGINE,)),
        ToolSpec("risk.on_date", "The risk-engine record of one area on one exact date. No other date is ever substituted.",
                 {"admin_unit_id": Arg("int", required=True, minimum=1), "date": Arg("date", required=True)}, (C.RISK_ENGINE,)),
        ToolSpec("risk.history", "Risk-engine records of one area inside a date window (newest first).",
                 {"admin_unit_id": Arg("int", required=True, minimum=1), "date_from": Arg("date"), "date_to": Arg("date"), "limit": Arg("int", minimum=1, maximum=100)},
                 (C.RISK_ENGINE,)),
        ToolSpec("risk.coverage", "Coverage / status information of the latest risk-engine record (data coverage, observed vs missing signals, threshold status, version).",
                 {"admin_unit_id": Arg("int", required=True, minimum=1)}, (C.RISK_ENGINE,)),
        ToolSpec("rag.retrieve", "Documentary evidence: passages of official reports retrieved by lexical, semantic or hybrid search (RAG). Documents are evidence, never risk inputs.",
                 {"query": Arg("str", required=True, free_text=True), "mode": Arg("enum", choices=RETRIEVAL_MODES), "admin_unit_id": uid,
                  "province": Arg("str", description="canonical province name"), "source": Arg("enum", choices=SOURCES), "event_type": Arg("str"),
                  "date_from": Arg("date"), "date_to": Arg("date"), "top_k": Arg("int", minimum=1, maximum=10)}, (C.RAG_DOCUMENT,)),
        ToolSpec("ml.predictions", "ML prediction-layer rows for one area: PREDICTED, BASELINE_ONLY (a simple baseline, NOT a validated ML model) or INSUFFICIENT_DATA.",
                 {"admin_unit_id": Arg("int", required=True, minimum=1), "horizon": Arg("int", minimum=1, maximum=30)}, (C.ML_MODEL, C.BASELINE_MODEL)),
        ToolSpec("ml.models", "Metadata of the current model runs (target, horizon, deployed predictor, validation against baselines, periods, metrics).",
                 {}, (C.ML_MODEL, C.BASELINE_MODEL)),
        ToolSpec("intelligence.ask", "The existing evidence-grounded intelligence service (risk context + documentary evidence + ML forecast, kept separate). "
                 "It never calls the agent.",
                 {"question": Arg("str", required=True, free_text=True), "admin_unit_id": uid, "date": Arg("date"), "mode": Arg("enum", choices=RETRIEVAL_MODES),
                  "top_k": Arg("int", minimum=1, maximum=10)}, (C.RISK_ENGINE, C.RAG_DOCUMENT, C.ML_MODEL, C.BASELINE_MODEL, C.GEOGRAPHY)),
    ]
    return {t.name: t for t in s}


TOOLS: dict[str, ToolSpec] = _specs()
TOOL_NAMES = tuple(TOOLS)
GEOGRAPHY_TOOLS = ("geography.resolve_place", "geography.get_admin_unit", "geography.list_units")


@dataclass
class ValidationResult:
    ok: bool
    arguments: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)          # [{"code": ..., "argument": ..., "detail": ...}]

    def reason(self) -> str:
        return "; ".join(f"{e['code']}" + (f" ({e['argument']})" if e.get("argument") else "") + (f": {e['detail']}" if e.get("detail") else "") for e in self.errors)


def _check(name: str, spec: Arg, value: Any) -> tuple[Any, Optional[dict]]:
    def err(code, detail=None):
        return None, {"code": code, "argument": name, "detail": detail}
    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return err("bad_type", "expected an integer")
        if spec.minimum is not None and value < spec.minimum or spec.maximum is not None and value > spec.maximum:
            return err("out_of_range", f"allowed {spec.minimum}..{spec.maximum}")
        return value, None
    if spec.kind == "bool":
        return (value, None) if isinstance(value, bool) else err("bad_type", "expected a boolean")
    if spec.kind in ("str", "enum", "date"):
        if not isinstance(value, str):
            return err("bad_type", "expected a string")
        v = value.strip()
        if _CTRL.search(v):
            return err("forbidden_content", "control characters")
        if spec.kind == "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                return err("bad_date", "expected YYYY-MM-DD")
            try:
                date.fromisoformat(v)
            except ValueError:
                return err("bad_date", "not a calendar date")
            return v, None
        if spec.kind == "enum":
            return (v, None) if v in spec.choices else err("not_allowed", f"one of {', '.join(spec.choices)}")
        if not v:
            return err("empty")
        if len(v) > MAX_TEXT:
            return err("too_long", f"at most {MAX_TEXT} characters")
        if spec.free_text:
            bad = scan_free_text(v)
            if bad:
                return err("forbidden_content", bad.code)
        elif not re.fullmatch(r"[\w .,&'\-()/]{1,80}", v) or re.search(r"https?:|//|;|--", v):
            return err("forbidden_content", "an identifier may contain only letters, digits, spaces and . , & ' - ( ) /")
        return v, None
    return err("unknown_kind")


def validate_call(tool_name: Any, arguments: Any) -> ValidationResult:
    """Validate a proposed call (from the deterministic router or from a model). Nothing here executes anything."""
    if not isinstance(tool_name, str) or tool_name not in TOOLS:
        return ValidationResult(False, errors=[{"code": "unknown_tool", "argument": None, "detail": f"{str(tool_name)[:60]!r} is not in the allowlist"}])
    if not isinstance(arguments, dict):
        return ValidationResult(False, errors=[{"code": "arguments_not_an_object", "argument": None, "detail": None}])
    spec = TOOLS[tool_name]
    errors, clean = [], {}
    for k in arguments:
        if k not in spec.args:
            errors.append({"code": "unknown_argument", "argument": str(k)[:40], "detail": f"{tool_name} accepts: {', '.join(spec.args) or 'no arguments'}"})
    for k, a in spec.args.items():
        if k not in arguments or arguments[k] is None:
            if a.required:
                errors.append({"code": "missing_argument", "argument": k, "detail": None})
            continue
        v, e = _check(k, a, arguments[k])
        if e:
            errors.append(e)
        else:
            clean[k] = v
    if not errors and clean.get("date_from") and clean.get("date_to") and clean["date_from"] > clean["date_to"]:
        errors.append({"code": "bad_range", "argument": "date_from", "detail": "date_from is after date_to"})
    return ValidationResult(not errors, clean if not errors else {}, errors)


def _model_tag(row: dict) -> Optional[str]:
    mt = row.get("model_type")
    if mt == "baseline" or row.get("status") == "BASELINE_ONLY":
        return C.BASELINE_MODEL
    if mt == "ml":
        return C.ML_MODEL
    return None


def provenance_for(tool_name: str, result: Any) -> dict:
    """The provenance of a tool result: which capability produced it (and, for ML rows, whether it was a validated model or a baseline)."""
    spec = TOOLS[tool_name]
    if tool_name in ("ml.predictions", "ml.models"):
        rows = (result or {}).get("predictions" if tool_name == "ml.predictions" else "models") or []
        srcs = []
        for r in rows:
            if r.get("status") == "INSUFFICIENT_DATA":
                continue
            tag = _model_tag(r)
            if tag and tag not in srcs:
                srcs.append(tag)
        return {"sources": srcs, "capability": tool_name,
                "note": "ML_MODEL = a validated ML model; BASELINE_MODEL = a simple baseline (not validated ML); INSUFFICIENT_DATA rows produce no prediction "
                        "and so carry no model provenance."}
    if tool_name == "intelligence.ask":
        r = result or {}
        srcs = []
        if (r.get("risk_context") or {}).get("status") == "AVAILABLE":
            srcs.append(C.RISK_ENGINE)
        if r.get("documentary_evidence"):
            srcs.append(C.RAG_DOCUMENT)
        for p in (r.get("ml_prediction") or {}).get("predictions", []):
            tag = _model_tag(p) or C.ML_MODEL
            if tag not in srcs:
                srcs.append(tag)
        return {"sources": srcs, "capability": tool_name, "note": "composite service; each component keeps its own provenance"}
    return {"sources": list(spec.provenance), "capability": tool_name}


def catalogue() -> list[dict]:
    """The allowlist as plain data (for documentation, the API response and the model-routing prompt)."""
    out = []
    for t in TOOLS.values():
        out.append({"tool_name": t.name, "description": t.description, "read_only": t.read_only, "provenance": list(t.provenance),
                    "arguments": {k: {"type": a.kind, "required": a.required, **({"choices": list(a.choices)} if a.choices else {}),
                                      **({"min": a.minimum} if a.minimum is not None else {}), **({"max": a.maximum} if a.maximum is not None else {})}
                                  for k, a in t.args.items()}})
    return out
