"""Read the project's EXISTING parsed document artifacts (read-only; nothing is scraped, copied or rewritten).

Each reader returns (source_docs, skipped). A source doc is the raw material for normalize.normalize_document:
the verbatim text plus whatever the source actually states. `skipped` lists records that could not become documents,
each with a reason (never silently dropped).
"""

from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote

PARSED = Path("data") / "parsed"


def _rel(path: str | Path, root: Path) -> str:
    return Path(path).resolve().relative_to(root.resolve()).as_posix()


def _json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl(path: str) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _src(**kw) -> dict:
    base = {"source": None, "source_type": None, "native_id": None, "title": None, "text": None, "text_fields": None,
            "date_text": None, "url": None, "file_path": None, "provinces_raw": [], "districts_raw": [], "jurisdiction": None,
            "geography_basis": None, "event_raw": [], "ingestion_timestamp": None, "parser_version": None,
            "published_at": None, "metadata": {}}
    base.update(kw)
    return base


def read_ndma_sitreps(root: Path) -> tuple[list[dict], list[dict]]:
    docs, skipped = [], []
    for p in sorted(glob.glob(str(root / PARSED / "ndma" / "sitreps" / "*.json"))):
        d = _json(p)
        stem = Path(p).stem
        if not (d.get("raw_text") or "").strip():
            skipped.append({"source": "ndma", "id": stem, "reason": "no extracted text"})
            continue
        docs.append(_src(source="ndma", source_type="sitrep", native_id=stem, title=d.get("subject"), text=d["raw_text"],
                         date_text=d.get("report_date"), file_path=_rel(p, root), provinces_raw=list(d.get("provinces") or []),
                         geography_basis="mentioned_in_text (parser-extracted province list)",
                         event_raw=list(d.get("weather_events") or []), ingestion_timestamp=d.get("parsed_at"),
                         metadata={"report_number": d.get("report_number"), "source_filename": d.get("filename"),
                                   "pages": d.get("pages"), "rivers_mentioned": d.get("rivers"), "dams_mentioned": d.get("dams"),
                                   "source_organization": d.get("source")}))
    return docs, skipped


def read_pdma_daily(root: Path) -> tuple[list[dict], list[dict]]:
    docs, skipped = [], []
    for p in sorted(glob.glob(str(root / PARSED / "pdma" / "daily" / "*" / "*.json"))):
        d = _json(p)
        sf = d.get("source_file") or Path(p).stem
        parts = [("forecast", d.get("forecast") or ""), ("weather_alert", d.get("weather_alert") or "")]
        parts = [(k, v) for k, v in parts if v.strip()]
        if not parts:
            skipped.append({"source": "pdma", "id": sf, "reason": "no forecast/alert text in the parsed report"})
            continue
        text, fields, pos = "", [], 0
        for i, (k, v) in enumerate(parts):
            if i:
                text += "\n\n"
                pos = len(text)
            fields.append({"field": k, "char_start": pos, "char_end": pos + len(v)})
            text += v
            pos = len(text)
        docs.append(_src(source="pdma", source_type="daily_report", native_id=Path(unquote(sf)).stem, title=Path(unquote(sf)).stem,
                         text=text, text_fields=fields, date_text=d.get("report_date"), file_path=_rel(p, root),
                         districts_raw=list(d.get("forecast_districts") or []), jurisdiction="Punjab",
                         geography_basis="issuing_authority_jurisdiction (PDMA Punjab) + districts_mentioned_in_text",
                         ingestion_timestamp=d.get("created_at"),
                         metadata={"report_time": d.get("report_time"), "report_year": d.get("report_year"), "source_file": sf,
                                   "text_quality_note": "PDF text-layer extraction of the forecast and alert boxes; columns may interleave",
                                   "dams_listed": d.get("dams")}))
    return docs, skipped


def read_canonical_documents(root: Path) -> tuple[list[dict], list[dict]]:
    docs, skipped = [], []
    for p in sorted(glob.glob(str(root / PARSED / "canonical" / "document" / "*.jsonl"))):
        for r in _jsonl(p):
            rid = r.get("source_record_id") or ""
            if not (r.get("text") or "").strip():
                skipped.append({"source": r.get("source"), "id": rid, "reason": "no extracted text"})
                continue
            prov = r.get("provenance") or {}
            url = prov.get("source_url_or_path")
            docs.append(_src(source=r["source"], source_type=r.get("doc_type"), native_id=rid.split(":")[-1], title=r.get("title"),
                             text=r["text"], date_text=r.get("report_date"), published_at=r.get("publication_date"),
                             url=url if isinstance(url, str) and url.startswith("http") else None,
                             file_path=r.get("source_document") or prov.get("source_document"), event_raw=[r["hazard_topic"]] if r.get("hazard_topic") else [],
                             geography_basis=None if not r.get("location_original") else "location_original",
                             provinces_raw=[r["location_original"]] if r.get("location_original") else [],
                             ingestion_timestamp=r.get("ingestion_timestamp"), parser_version=prov.get("parser_version"),
                             metadata={"source_record_id": rid, "page_count": r.get("page_count"), "issuing_organization": r.get("issuing_organization"),
                                       "period_start": r.get("period_start"), "period_end": r.get("period_end"),
                                       "text_quality_note": r.get("text_quality_note"), "script_stated": r.get("script"),
                                       "artifact_sha256": prov.get("sha256"), "retrieved_at": prov.get("retrieved_at"),
                                       "resolution_notes": r.get("resolution_notes")}))
    return docs, skipped


def read_pmd_alert(root: Path) -> tuple[list[dict], list[dict]]:
    p = root / PARSED / "pmd" / "weather_alerts" / "latest.json"
    if not p.exists():
        return [], []
    d = _json(str(p))
    text = d.get("forecast") or ""
    if not text.strip():
        return [], [{"source": "pmd", "id": "weather_alert", "reason": "no forecast text"}]
    return [_src(source="pmd", source_type="weather_alert", native_id=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], title=None,
                 text=text, file_path=_rel(p, root), provinces_raw=list(d.get("regions") or []),
                 geography_basis="mentioned_in_text (alert region list)", event_raw=[d["alert_type"]] if d.get("alert_type") else [],
                 ingestion_timestamp=d.get("scraped_at"),
                 metadata={"severity": d.get("severity"), "duration": d.get("duration"), "category": d.get("category"),
                           "scraped_at": d.get("scraped_at"),
                           "note": "PMD publishes no issue date in this record; scraped_at is a retrieval time, not a publication date"})], []


def read_pmd_weekly(root: Path) -> tuple[list[dict], list[dict]]:
    p = root / PARSED / "pmd" / "weekly_outlook" / "latest.json"
    if not p.exists():
        return [], []
    docs, skipped = [], []
    for i, d in enumerate(_json(str(p))):
        text = d.get("weather_summary") or ""
        if not text.strip():
            skipped.append({"source": "pmd", "id": f"weekly_outlook[{i}]", "reason": "no summary text"})
            continue
        key = hashlib.sha256(((d.get("date") or "") + "\n" + text).encode("utf-8")).hexdigest()[:16]
        docs.append(_src(source="pmd", source_type="weekly_outlook", native_id=key, title=None, text=text, date_text=d.get("date"),
                         file_path=_rel(p, root), provinces_raw=list(d.get("regions") or []),
                         geography_basis="mentioned_in_text (outlook region list)", ingestion_timestamp=d.get("scraped_at"),
                         metadata={"weekday": d.get("weekday"), "category": d.get("category"), "scraped_at": d.get("scraped_at"),
                                   "language_note": "Urdu text as published"}))
    return docs, skipped


READERS = [("ndma_sitreps", read_ndma_sitreps), ("pdma_daily", read_pdma_daily), ("canonical_documents", read_canonical_documents),
           ("pmd_weather_alert", read_pmd_alert), ("pmd_weekly_outlook", read_pmd_weekly)]


def discover_non_document_artifacts(root: Path) -> list[dict]:
    """Parsed artifacts that exist but are NOT narrative documents, counted so nothing is silently ignored."""
    out = []

    def add(rel: str, reason: str, loader):
        p = root / rel
        if p.exists():
            out.append({"artifact": rel, "records": len(loader(str(p))), "reason": reason})

    add("data/parsed/pmd/daily_forecast/latest.json", "structured per-city forecast rows (no narrative text)", _json)
    add("data/parsed/tier1/suparco/campaigns.jsonl", "short campaign metadata (name/description), not a report document", _jsonl)
    add("data/parsed/tier1/ffc/reservoir_levels.jsonl", "structured reservoir level observations", _jsonl)
    add("data/parsed/tier1/epa_punjab_aqi/aqi_observations.jsonl", "structured AQI observations", _jsonl)
    p = root / "data/parsed/tier1/ffc/dfsr_glof.jsonl"
    if p.exists():
        n = sum(1 for r in _jsonl(str(p)) if r.get("record_kind") != "document")
        out.append({"artifact": "data/parsed/tier1/ffc/dfsr_glof.jsonl", "records": n,
                    "reason": "per-province rows derived from a GLOF alert document that is already ingested as a document"})
    return out
