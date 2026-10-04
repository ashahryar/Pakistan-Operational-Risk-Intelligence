"""Task 34 -- DETERMINISTIC intent routing and planning (no language model; this is the default and the fallback).

`analyze` turns the question into explicit facets (risk / forecast / documents / explanation / geography lookup) with plain regular expressions and the
existing pure helpers of the intelligence layer (dates, event types). `intent_for` maps the facets to one of the supported intents. `build_plan` turns an
intent plus the (already resolved) geography into an ordered list of allowlisted tool calls. Same input -> same plan, always.

Nothing here resolves a place: geography is resolved by the geography tool (existing exact/alias/normalised resolver, never fuzzy), and a place that is
named but not recognised is surfaced (`unrecognized_places`) instead of being guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from pipeline.agents import contracts as C
from pipeline.agents.contracts import PlannedCall
from pipeline.intelligence.context import LATEST_WORDS, MONTHS, RISK_INTENT, find_dates, find_events
from scripts.geo.resolver import normalize_name

I = re.I

FORECAST = re.compile(r"\b(?:forecast\w*|predict\w*|projected|projections?|tomorrow|next (?:\d+ )?(?:days?|week)|coming (?:days|week)|in (?:the next )?\d+ days?|\d+[- ]days? (?:ahead|forecast))\b", I)
AQI = re.compile(r"\b(?:aqi|air[- ]quality|air pollution|pollution|smog|pm ?2\.?5|particulates?)\b", I)
OTHER_TARGET = re.compile(r"\b(rainfall|rain|flood\w*|river levels?|water levels?|discharge|gauge|temperature|heat ?waves?|weather|wind|humidity|earthquakes?|landslides?|drought)\b", I)
DOCS = re.compile(r"\b(?:report(?:ed|s|ing)?|ndma|pdma|pmd|ffc|suparco|sitreps?|situation reports?|advisor(?:y|ies)|bulletins?|documents?|according to|said|mention(?:ed|s)?|evidence|official)\b", I)
WHY = re.compile(r"\b(?:why|explain|how come|reason|what explains|what caused|because)\b", I)
COVERAGE = re.compile(r"\b(?:coverage|how much data|data quality|confidence|observed signals?|missing signals?|threshold status|calculation version)\b", I)
GEO_LOOKUP = [re.compile(p, I) for p in (
    r"\b(?:which|what)\s+(?:province|district)\b", r"\b(?:list|show|name|give me|what are)\b.{0,25}\b(?:districts?|provinces?)\b", r"\bis\s+[\w .'-]{2,40}?\s+(?:a|an|in)\s+(?:province|district)\b",
    r"\b(?:districts?|provinces?)\b.{0,12}\b(?:of|in|under)\b", r"\b(?:admin(?:istrative)? units?|boundar(?:y|ies)|canonical)\b", r"\bwhere is\b")]
SOURCE_WORDS = {"ndma": "ndma", "pdma": "pdma", "pmd": "pmd", "ffc": "ffc"}
_STATUS_MENTION = re.compile(r"\b(INSUFFICIENT_DATA|NO_SIGNAL|CRITICAL|MODERATE|HIGH|LOW)\b")
_STATUS_WORD = re.compile(r"\b(?:classified|rated|marked|labelled|labeled|categori[sz]ed|status(?: is| of)?|risk (?:is|level is)|at)\s+(?:as\s+)?(critical|moderate|high|low)\b", I)
_HORIZON = [re.compile(p, I) for p in (r"\b(\d+)[- ]days?\b", r"\bin (?:the next )?(\d+) days?\b", r"\bnext (\d+) days\b")]

STOP_CAPS = {m for m in MONTHS} | {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "the", "this", "that", "these", "those",
                                    "district", "division", "city", "province", "region", "area", "town", "capital", "territory", "state", "july", "today"}
_PLACE_AFTER = re.compile(r"\b(?:in|for|at|near|around|within|from|of|about)\s+((?:[A-Z][\w'’]*(?:[ -](?:[A-Z][\w'’]*|of|ul|ud|e))*))")
_IS_A = re.compile(r"\bis\s+([A-Z][\w'’]*(?:\s+[A-Z][\w'’]*)*)\s+(?:a|an|in)\s+(?:province|district)\b")


@dataclass
class Analysis:
    question: str
    facets: dict = field(default_factory=dict)                 # risk | forecast | docs | why | geography | coverage
    date: Optional[str] = None                                 # a single day (explicit parameter wins over the question)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    latest_requested: bool = False
    events: list = field(default_factory=list)
    source: Optional[str] = None
    horizon: Optional[int] = None
    forecast_target: Optional[str] = None                      # air_quality_index | None (unspecified) | "unsupported:<word>"
    stated_status: Optional[str] = None                        # a risk status asserted by the question (false-premise check)
    intent: str = C.UNSUPPORTED
    reason: Optional[str] = None                               # why UNSUPPORTED

    def to_dict(self) -> dict:
        return {"facets": self.facets, "date": self.date, "date_from": self.date_from, "date_to": self.date_to, "latest_requested": self.latest_requested,
                "events": self.events, "source": self.source, "horizon": self.horizon, "forecast_target": self.forecast_target,
                "stated_status": self.stated_status, "intent": self.intent, "reason": self.reason}


def _horizon(q: str) -> Optional[int]:
    if re.search(r"\btomorrow\b", q, I):
        return 1
    if re.search(r"\bnext week\b|\bcoming week\b", q, I):
        return 7
    for pat in _HORIZON:
        m = pat.search(q)
        if m:
            return int(m.group(1))
    return None


def _forecast_target(q: str) -> Optional[str]:
    if AQI.search(q):
        return "air_quality_index"
    other = OTHER_TARGET.search(q)
    return f"unsupported:{other.group(1).lower()}" if other else None


def _stated_status(q: str) -> Optional[str]:
    m = _STATUS_MENTION.search(q)
    if m:
        return m.group(1)
    m = _STATUS_WORD.search(q)
    return m.group(1).upper() if m else None


def analyze(question: str, explicit_date: Optional[str] = None) -> Analysis:
    q = " ".join((question or "").split())
    d = find_dates(q)
    events = find_events(q)
    risk = bool(RISK_INTENT.search(q))
    forecast = bool(FORECAST.search(q))
    docs = bool(DOCS.search(q)) or (bool(events) and not risk and not forecast)
    geo = any(p.search(q) for p in GEO_LOOKUP)
    srcs = {SOURCE_WORDS[w.lower()] for w in re.findall(r"\b(?:NDMA|PDMA|PMD|FFC)\b", q, I)}
    a = Analysis(q, {"risk": risk, "forecast": forecast, "docs": docs, "why": bool(WHY.search(q)), "geography": geo, "coverage": bool(COVERAGE.search(q))},
                 date=explicit_date or d["date"], date_from=d["date_from"], date_to=d["date_to"], latest_requested=bool(LATEST_WORDS.search(q)), events=events,
                 source=next(iter(srcs)) if len(srcs) == 1 else None, horizon=_horizon(q) if forecast else None,
                 forecast_target=_forecast_target(q) if forecast else None, stated_status=_stated_status(q))
    a.intent, a.reason = intent_for(a)
    return a


def intent_for(a: Analysis) -> tuple[str, Optional[str]]:
    f = a.facets
    risk, forecast, docs, why, geo = f["risk"], f["forecast"], f["docs"], f["why"], f["geography"]
    if geo and not (risk or forecast or docs):
        return C.GEOGRAPHY_LOOKUP, None
    n = sum((risk, forecast, docs))
    if n == 0:
        if AQI.search(a.question):
            return C.UNSUPPORTED, "observed air-quality readings are not an agent tool; ask for the AQI forecast or for the risk context"
        return C.UNSUPPORTED, "the question matches no supported capability (risk status, documentary evidence, ML/baseline forecast, geography lookup)"
    if (risk and (forecast or docs)) or (forecast and docs):
        return C.COMBINED_INTELLIGENCE, None
    if risk and why:
        return C.EVIDENCE_GROUNDED_QUESTION, None
    if risk:
        return (C.HISTORICAL_RISK if (a.date or a.date_from) else C.CURRENT_RISK), None
    if forecast:
        return C.ML_FORECAST, None
    return C.DOCUMENT_SEARCH, None


def asks_for_provinces(question: str) -> bool:
    return bool(re.search(r"\b(?:list|show|name|give me|what are)\b.{0,25}\bprovinces\b|\ball provinces\b|\bwhich provinces\b", question, I))


def unrecognized_places(question: str, mentions: list) -> list[str]:
    """Capitalised place-like phrases after a preposition that the canonical resolver did NOT recognise (e.g. 'Kabul', 'Marala Barrage', 'Pakistan').
    Heuristic by design: it only decides that the agent must not pretend to know the place; it never maps a place to an area."""
    known = {normalize_name(m["raw"]) for m in mentions if m.get("raw")}
    known_tokens = {t for k in known for t in k.split()}
    out = []
    spans = [m.group(1) for m in _PLACE_AFTER.finditer(question)] + [m.group(1) for m in _IS_A.finditer(question)]
    for span in spans:
        toks = [re.sub(r"(?:'s|’s)$", "", t) for t in re.split(r"[ ]+", span.strip())]
        toks = [t for t in toks if t]
        while toks and toks[-1].lower() in ("of", "ul", "ud", "e"):
            toks.pop()
        kept = [t for t in toks if not (t.isupper() and len(t) >= 2) and t.lower() not in STOP_CAPS]
        if not kept:
            continue
        phrase = " ".join(kept)
        key = normalize_name(phrase)
        if key in known or all(normalize_name(t) in known_tokens for t in kept):
            continue
        out.append(phrase)
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------------------------------------------------------------------- planning
def needs_unit(intent: str) -> bool:
    return intent in (C.CURRENT_RISK, C.HISTORICAL_RISK, C.ML_FORECAST, C.EVIDENCE_GROUNDED_QUESTION, C.COMBINED_INTELLIGENCE)


def build_plan(a: Analysis, unit: Optional[dict], province: Optional[dict], mode: str, top_k: int, explicit_unit: bool = False) -> list[PlannedCall]:
    """The ordered tool calls for the intent. `unit` / `province` come from the geography step (None when the intent needs no area)."""
    uid = unit["id"] if unit else None
    plan: list[PlannedCall] = []
    if a.intent == C.GEOGRAPHY_LOOKUP:
        if unit:
            plan.append(PlannedCall("geography.get_admin_unit", {"admin_unit_id": uid}))
        if re.search(r"\b(?:list|show|name|give me|what are|districts? (?:of|in)|provinces?)\b", a.question, I) and unit and unit["level"] == 1:
            plan.append(PlannedCall("geography.list_units", {"level": 2, "province": unit["name"], "limit": 200}))
        elif asks_for_provinces(a.question) and not unit:
            plan.append(PlannedCall("geography.list_units", {"level": 1, "limit": 50}))
        return plan
    risk_call = _risk_call(a, uid)
    if a.intent in (C.CURRENT_RISK, C.HISTORICAL_RISK):
        plan.append(risk_call)
        if a.facets.get("coverage"):
            plan.append(PlannedCall("risk.coverage", {"admin_unit_id": uid}))
    elif a.intent == C.ML_FORECAST:
        plan.extend(_ml_calls(a, uid))
    elif a.intent == C.DOCUMENT_SEARCH:
        plan.append(_rag_call(a, unit, province, mode, top_k))
    elif a.intent == C.EVIDENCE_GROUNDED_QUESTION:
        args = {"question": a.question, "admin_unit_id": uid, "mode": mode, "top_k": top_k}
        if a.date:
            args["date"] = a.date
        plan.append(PlannedCall("intelligence.ask", args))
    elif a.intent == C.COMBINED_INTELLIGENCE:
        f = a.facets
        if f["risk"]:
            plan.append(risk_call)
            if f["coverage"]:
                plan.append(PlannedCall("risk.coverage", {"admin_unit_id": uid}))
        if f["docs"] or (f["why"] and f["risk"]):
            plan.append(_rag_call(a, unit, province, mode, top_k))
        if f["forecast"]:
            plan.extend(_ml_calls(a, uid))
    return plan


def _risk_call(a: Analysis, uid: Optional[int]) -> PlannedCall:
    if a.date:
        return PlannedCall("risk.on_date", {"admin_unit_id": uid, "date": a.date})
    if a.date_from or a.date_to:
        args = {"admin_unit_id": uid, "limit": 31}
        if a.date_from:
            args["date_from"] = a.date_from
        if a.date_to:
            args["date_to"] = a.date_to
        return PlannedCall("risk.history", args)
    return PlannedCall("risk.latest", {"admin_unit_id": uid})


def _ml_calls(a: Analysis, uid: Optional[int]) -> list[PlannedCall]:
    if a.forecast_target and a.forecast_target.startswith("unsupported:"):
        return [PlannedCall("ml.models", {})]                       # no model exists for the asked target: show what does exist, never substitute
    args = {"admin_unit_id": uid}
    if a.horizon and 1 <= a.horizon <= 30:
        args["horizon"] = a.horizon
    return [PlannedCall("ml.predictions", args)]


def rag_arguments(a: Analysis, unit: Optional[dict], province: Optional[dict], mode: str, top_k: int) -> dict:
    """The strictest retrieval arguments; the orchestrator relaxes inferred filters in the existing order (event_type -> district_to_province -> date)."""
    args: dict = {"query": a.question, "mode": mode, "top_k": top_k}
    if unit and unit["level"] == 2:
        args["admin_unit_id"] = unit["id"]
    elif province:
        args["province"] = province["name"]
    if len(a.events) == 1:
        args["event_type"] = a.events[0]
    if a.date:
        args["date_from"] = args["date_to"] = a.date
    else:
        if a.date_from:
            args["date_from"] = a.date_from
        if a.date_to:
            args["date_to"] = a.date_to
    if a.source:
        args["source"] = a.source
    return args


def _rag_call(a: Analysis, unit, province, mode, top_k) -> PlannedCall:
    return PlannedCall("rag.retrieve", rag_arguments(a, unit, province, mode, top_k))


def premise_check(stated: Optional[str], record: Optional[dict]) -> Optional[dict]:
    """False-premise handling: if the question asserts a risk status, compare it with the engine's actual status. The engine value always wins."""
    if not stated or not record:
        return None
    actual = record.get("risk_status")
    return {"stated_status": stated, "engine_status": actual, "matches": stated == actual, "risk_date": record.get("risk_date"),
            "note": ("The question's stated status matches the risk engine record." if stated == actual else
                     f"The question assumes {stated}, but the risk engine reports {actual} (risk date {record.get('risk_date')}). The engine value is the one shown.")}
