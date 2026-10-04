"""Source document -> canonical RAG document. Deterministic: no wall clock, no randomness. Missing metadata stays None."""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from typing import Optional

from pipeline.rag.contracts import NORMALIZATION_VERSION, make_document_id, sha256_text
from pipeline.rag.geography import resolve_districts, resolve_provinces, summarize_geography

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_DATE_RE = re.compile(r"\s*(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]+)\.?,?\s+(\d{4})\s*", re.IGNORECASE)
_ISO_RE = re.compile(r"\s*(\d{4})-(\d{2})-(\d{2})\s*$")

EVENT_MAP = {"flood": "flood", "flash flood": "flash_flood", "rain": "rainfall", "heavy rain": "heavy_rainfall", "heatwave": "heatwave",
             "landslide": "landslide", "cloudburst": "cloudburst", "glacial lake": "glacial_lake", "drought": "drought",
             "earthquake": "earthquake", "cyclone": "cyclone"}


def parse_document_date(text: Optional[str]) -> tuple[Optional[str], str]:
    """-> (ISO date | None, basis). Only a date that is stated unambiguously is returned; anything else is None
    ('unparseable') -- never defaulted, never guessed (dd.mm.yyyy is rejected because its order is ambiguous)."""
    if text is None or not str(text).strip():
        return None, "not_stated"
    s = str(text)
    try:
        m = _ISO_RE.match(s)
        if m:
            return _dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat(), "report_date"
        m = _DATE_RE.fullmatch(s)
        if m and m[2].lower() in _MONTHS:
            return _dt.date(int(m[3]), _MONTHS[m[2].lower()], int(m[1])).isoformat(), "report_date"
    except ValueError:
        pass
    return None, "unparseable"


def normalize_events(raw: list[str]) -> dict:
    types = sorted({EVENT_MAP.get(str(r).strip().lower(), re.sub(r"\W+", "_", str(r).strip().lower()).strip("_")) for r in raw if str(r).strip()})
    return {"event_type": types[0] if len(types) == 1 else None, "event_types": types, "event_type_raw": [str(r) for r in raw]}


def script_of(text: str) -> str:
    """Factual character-script measurement of the text ('latin' | 'arabic' | 'mixed' | 'other')."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "other"
    arabic = sum(1 for c in letters if "ARABIC" in unicodedata.name(c, ""))
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    if arabic / len(letters) > 0.8:
        return "arabic"
    if latin / len(letters) > 0.8:
        return "latin"
    return "mixed" if arabic and latin else "other"


def normalize_document(src: dict, unit_lookup: Optional[dict[str, int]] = None) -> dict:
    lookup = unit_lookup or {}
    text = src["text"]
    date_iso, basis = parse_document_date(src.get("date_text"))
    jurisdiction = None
    if src.get("jurisdiction"):
        jurisdiction = {"raw": src["jurisdiction"], "name": src["jurisdiction"], "admin_unit_id": lookup.get(src["jurisdiction"]),
                        "status": "resolved", "match_method": "issuing_authority"}
    geo = summarize_geography(resolve_provinces(src.get("provinces_raw") or [], lookup),
                              resolve_districts(src.get("districts_raw") or [], lookup), jurisdiction)
    meta = dict(src.get("metadata") or {})
    if src.get("text_fields"):
        meta["text_fields"] = src["text_fields"]
    return {
        "document_id": make_document_id(src["source"], src["source_type"], src["native_id"]),
        "source": src["source"], "source_type": src["source_type"], "title": src.get("title"),
        "document_date": date_iso, "document_date_text": src.get("date_text"), "document_date_basis": basis,
        "published_at": src.get("published_at"), "url": src.get("url"), "file_path": src.get("file_path"),
        **geo, "geography_basis": src.get("geography_basis"), **normalize_events(src.get("event_raw") or []),
        "language_script": script_of(text), "raw_text": text, "content_sha256": sha256_text(text), "metadata": meta,
        "ingestion_timestamp": src.get("ingestion_timestamp"), "parser_version": src.get("parser_version"),
        "normalization_version": NORMALIZATION_VERSION,
    }
