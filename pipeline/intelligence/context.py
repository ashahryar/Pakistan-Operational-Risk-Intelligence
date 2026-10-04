"""Deterministic question-context extraction for the intelligence layer: place, date and event type from the question text.

No language model is used. Places are resolved against the project's canonical geography (scripts/geo/canonical_data.py names and aliases,
normalised with the existing scripts/geo/resolver.normalize_name) and only EXACT / ALIAS / NORMALISED matches are accepted -- fuzzy
matching is never used on free text. A name that matches more than one canonical unit (for example "Islamabad": an alias of the Islamabad
Capital Territory province AND a district) is reported as AMBIGUOUS and is not guessed; a name that matches nothing is not mentioned at all;
caveated seed rows (not real districts) are kept as unresolved text. Gauge-station mappings are not used.
Pure functions: the caller supplies the admin-unit rows (id, level, name, province) read from geo.admin_unit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from scripts.geo.canonical_data import DISTRICTS, PROVINCES
from scripts.geo.resolver import normalize_name

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                      "november", "december"], start=1)}
_MONTH_RE = "|".join(MONTHS)
_STOP = frozenset("a an and are as at be by did do does for from how in is it of on or the to was what when where which who why with".split())
LATEST_WORDS = re.compile(r"\b(today|currently|current|now|latest|right now)\b", re.I)

# (pattern, event_type) -- the event types used in rag.documents; longest phrase first
EVENT_PATTERNS = [
    (r"flash[ -]?floods?", "flash_flood"), (r"glacial lake outburst|\bglofs?\b", "glof"), (r"heat ?waves?", "heatwave"),
    (r"landslides?|land slides?", "landslide"), (r"cloud ?bursts?", "cloudburst"), (r"droughts?", "drought"),
    (r"heavy rain(?:fall|s)?", "heavy_rainfall"), (r"\bfloods?\b|\bflooding\b|inundation", "flood"), (r"\brain(?:fall|s)?\b", "rainfall"),
]
RISK_INTENT = re.compile(r"\b(risk|classif\w*|operational (?:conditions?|status)|risk status|signals?)\b", re.I)


@dataclass
class QuestionContext:
    question: str
    geography_status: str = "not_stated"                      # resolved | ambiguous | multiple | unresolved | not_stated
    admin_unit: Optional[dict] = None                         # {id, level, name, province, match_method, raw}
    province: Optional[dict] = None                           # {id, name} (the unit itself when level 1, else its parent)
    mentions: list[dict] = field(default_factory=list)        # every place mention with its status; original text preserved
    date: Optional[str] = None                                # a single day (ISO)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    date_text: Optional[str] = None
    latest_requested: bool = False
    event_types: list[str] = field(default_factory=list)
    risk_intent: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"geography_status": self.geography_status, "admin_unit": self.admin_unit, "province": self.province, "mentions": self.mentions,
                "date": self.date, "date_from": self.date_from, "date_to": self.date_to, "date_text": self.date_text,
                "latest_requested": self.latest_requested, "event_types": self.event_types, "risk_intent": self.risk_intent, "notes": self.notes}


# ------------------------------------------------------------------------------------------------ geography
def build_index(units: list[dict]) -> dict[str, list[dict]]:
    """normalised name/alias -> [{level, name, id, province, method, caveat}] over canonical names present in `units`."""
    by_key = {(u["level"], u["name"]): u for u in units}
    index: dict[str, list[dict]] = {}

    def add(level, name, province, alias_of=None, caveat=None):
        unit = by_key.get((level, alias_of or name))
        if unit is None:
            return
        entry = {"level": level, "name": unit["name"], "id": unit["id"], "province": unit.get("province") or (unit["name"] if level == 1 else province),
                 "method": "alias" if alias_of else "exact", "caveat": caveat}
        index.setdefault(normalize_name(name), [])
        if all(e["id"] != entry["id"] for e in index[normalize_name(name)]):
            index[normalize_name(name)].append(entry)

    for p in PROVINCES:
        add(1, p["name"], p["name"])
        for a in p.get("aliases", []):
            add(1, a, p["name"], alias_of=p["name"])
    for d in DISTRICTS:
        add(2, d["name"], d["province"], caveat=d.get("caveat"))
        for a in d.get("aliases", []):
            add(2, a, d["province"], alias_of=d["name"], caveat=d.get("caveat"))
    return index


def _tokens(text: str) -> list[str]:
    out = []
    for raw in text.split():
        t = re.sub(r"(?:'s|’s)$", "", raw.strip("?,;:!()\"'“”‘’[]"))
        if t:
            out.append(t)
    return out


def find_places(question: str, index: dict[str, list[dict]]) -> list[dict]:
    toks = _tokens(question)
    used = [False] * len(toks)
    mentions = []
    for n in range(5, 0, -1):
        for i in range(0, len(toks) - n + 1):
            if any(used[i:i + n]):
                continue
            gram = " ".join(toks[i:i + n])
            if all(t.lower() in _STOP for t in toks[i:i + n]) or len(gram) < 3:
                continue
            hits = index.get(normalize_name(gram))
            if not hits:
                continue
            for j in range(i, i + n):
                used[j] = True
            real = [h for h in hits if not h["caveat"]]
            if not real:
                mentions.append({"raw": gram, "status": "unresolved", "match_method": "caveated_seed_unit", "candidates": []})
            elif len(real) > 1:
                mentions.append({"raw": gram, "status": "ambiguous", "match_method": "ambiguous",
                                 "candidates": [{"id": h["id"], "name": h["name"], "level": h["level"]} for h in real]})
            else:
                h = real[0]
                method = "exact" if gram == h["name"] else ("alias" if h["method"] == "alias" else "normalized")
                mentions.append({"raw": gram, "status": "resolved", "match_method": method,
                                 "candidates": [{"id": h["id"], "name": h["name"], "level": h["level"], "province": h["province"]}]})
    return mentions


def resolve_geography(mentions: list[dict], units: list[dict]) -> tuple[str, Optional[dict], Optional[dict], list[str]]:
    notes = []
    resolved = [m for m in mentions if m["status"] == "resolved"]
    if not mentions:
        return "not_stated", None, None, notes
    if any(m["status"] == "ambiguous" for m in mentions):
        notes.append("an ambiguous place name was not resolved; no area is assumed (pass admin_unit_id to choose)")
        return "ambiguous", None, None, notes
    if not resolved:
        return "unresolved", None, None, notes
    districts = {m["candidates"][0]["id"]: (m, m["candidates"][0]) for m in resolved if m["candidates"][0]["level"] == 2}
    provinces = {m["candidates"][0]["id"]: (m, m["candidates"][0]) for m in resolved if m["candidates"][0]["level"] == 1}
    if len(districts) > 1 or (not districts and len(provinces) > 1):
        notes.append("several different places were mentioned; no single area is assumed")
        return "multiple", None, None, notes
    if districts:
        (m, c), = districts.values()
        prov_name = c.get("province")
        if provinces and all(v[1]["name"] != prov_name for v in provinces.values()):
            notes.append("the district and the province mentioned do not match; no single area is assumed")
            return "multiple", None, None, notes
        prov = next((u for u in units if u["level"] == 1 and u["name"] == prov_name), None)
        unit = {"id": c["id"], "level": 2, "name": c["name"], "province": prov_name, "match_method": m["match_method"], "raw": m["raw"]}
        return "resolved", unit, ({"id": prov["id"], "name": prov["name"]} if prov else None), notes
    (m, c), = provinces.values()
    unit = {"id": c["id"], "level": 1, "name": c["name"], "province": c["name"], "match_method": m["match_method"], "raw": m["raw"]}
    return "resolved", unit, {"id": c["id"], "name": c["name"]}, notes


# ------------------------------------------------------------------------------------------------ dates
def _mk(y, m, d) -> Optional[str]:
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def _month_range(y: int, m: int) -> tuple[str, str]:
    last = (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days
    return date(y, m, 1).isoformat(), date(y, m, last).isoformat()


def find_dates(question: str) -> dict:
    """First explicit date in the text. Day-first for numeric dates (CLAUDE.md: 12.07.2026 is 12 July). Returns date | date_from/date_to | text."""
    q = question
    pats = [
        (r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: _mk(m[1], m[2], m[3])),
        (r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", lambda m: _mk(m[3], m[2], m[1])),
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\s*,?\s*(\d{{4}})\b", lambda m: _mk(m[3], MONTHS[m[2].lower()], m[1])),
        (rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b", lambda m: _mk(m[3], MONTHS[m[1].lower()], m[2])),
    ]
    for pat, fn in pats:
        m = re.search(pat, q, re.I)
        if m:
            d = fn(m)
            if d:
                return {"date": d, "date_from": None, "date_to": None, "text": m.group(0)}
    m = re.search(rf"\b({_MONTH_RE})\s+(\d{{4}})\b", q, re.I)
    if m:
        a, b = _month_range(int(m[2]), MONTHS[m[1].lower()])
        return {"date": None, "date_from": a, "date_to": b, "text": m.group(0)}
    return {"date": None, "date_from": None, "date_to": None, "text": None}


def find_events(question: str) -> list[str]:
    taken, hits = [], []
    for pat, ev in EVENT_PATTERNS:                                  # longest phrases first so "flash flood" is not also "flood"
        for m in re.finditer(pat, question, re.I):
            if not any(a < m.end() and m.start() < b for a, b in taken):
                taken.append((m.start(), m.end()))
                hits.append((m.start(), ev))
    return list(dict.fromkeys(ev for _, ev in sorted(hits)))


def extract_context(question: str, units: list[dict]) -> QuestionContext:
    mentions = find_places(question, build_index(units))
    status, unit, prov, notes = resolve_geography(mentions, units)
    d = find_dates(question)
    return QuestionContext(question=question, geography_status=status, admin_unit=unit, province=prov, mentions=mentions, date=d["date"],
                           date_from=d["date_from"], date_to=d["date_to"], date_text=d["text"], latest_requested=bool(LATEST_WORDS.search(question)),
                           event_types=find_events(question), risk_intent=bool(RISK_INTENT.search(question)), notes=notes)
