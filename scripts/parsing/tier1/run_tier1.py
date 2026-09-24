"""Task 19 -- run every Tier-1 parser over the Task 15 raw artifacts and emit coverage counts.

raw (read-only) -> source-specific parsed JSONL -> canonical JSONL -> coverage report.

Nothing under data/raw is written. Output is deterministic and idempotent: records are de-duplicated
by stable source_record_id (earliest retrieval wins), sorted, and written whole, and no wall-clock
value is embedded, so re-running on the same raw files yields byte-identical output.

Quarantine: failures and canonical rejections are collected through the same sink signature that
`pipeline.utils.quarantine.write_quarantine` uses. By default they are written to
data/parsed/tier1/quarantine.jsonl (a DB write per run would duplicate rows on every re-run);
`--db-quarantine` routes them to the real `dq.quarantine` via `write_quarantine` instead.

Usage: python scripts/parsing/tier1/run_tier1.py [--no-db] [--db-quarantine]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.canonical import tier1_adapters as adapters  # noqa: E402
from pipeline.canonical.output import write_jsonl  # noqa: E402
from scripts.parsing.tier1 import PARSER_VERSION, epa_aqi, ffc_dfsr, ffc_reservoir, pmd_ndmc, suparco  # noqa: E402
from scripts.parsing.tier1.artifacts import RAW_ROOT, discover_artifacts  # noqa: E402

PARSED_ROOT = PROJECT_ROOT / "data" / "parsed" / "tier1"
CANONICAL_ROOT = PROJECT_ROOT / "data" / "parsed" / "canonical"


def _dedupe(records):
    """One record per source_record_id; the earliest-retrieved artifact wins (stable tie-break)."""
    best = {}
    for rec in records:
        key = rec["source_record_id"]
        rank = (rec["artifact"].get("retrieved_at") or "", rec["artifact"].get("source_file") or "")
        if key not in best or rank < best[key][0]:
            best[key] = (rank, rec)
    return [best[k][1] for k in sorted(best)]


def _geo_counts(canonical):
    counts = Counter()
    for rec in canonical:
        status = rec.get("resolution_status")
        if status == "not_attempted":
            counts["not_attempted"] += 1
        elif rec.get("location_original") is None:
            counts["no_location"] += 1
        else:
            counts[status] += 1
    return {k: counts.get(k, 0) for k in ("resolved", "ambiguous", "unresolved", "no_location", "not_attempted")}


def _run_dataset(name, artifacts, handlers, adapt, sink):
    """handlers: {filename_or_suffix_predicate: parse_fn}. Returns (result, parsed_unique, canonical_by_domain)."""
    result = {"dataset": name, "raw_files_found": len(artifacts), "files_parseable": 0, "files_failed": 0,
              "files_not_in_scope": 0, "records_extracted": 0}
    parsed, quarantined = [], 0
    for art in artifacts:
        fn = next((f for pred, f in handlers if pred(art)), None)
        if fn is None:
            result["files_not_in_scope"] += 1
            continue
        recs, fails = fn(art)
        result["records_extracted"] += len(recs)
        parsed.extend(recs)
        if fails:
            result["files_failed"] += 1
        if recs:
            result["files_parseable"] += 1
        for f in fails:
            sink(source=name, domain="tier1_parse", source_document=f["source_document"], reason_code=f["reason_code"],
                 message=f["message"], parser_version=PARSER_VERSION, raw_payload=f["raw_payload"])
            quarantined += 1
    unique = _dedupe(parsed)
    result["records_unique"] = len(unique)
    result["duplicates_collapsed"] = len(parsed) - len(unique)
    counter = _Counter(sink)
    canonical = adapt(unique, counter)
    quarantined += counter.n
    result["records_quarantined"] = quarantined
    flat = [r for recs in canonical.values() for r in recs]
    result["records_canonicalized"] = len(flat)
    result["canonical_domains"] = {d: len(r) for d, r in sorted(canonical.items())}
    result["geography"] = _geo_counts(flat)
    return result, unique, canonical


class _Counter:
    """Wraps a quarantine sink to count canonical-stage rejections."""

    def __init__(self, sink):
        self.sink, self.n = sink, 0

    def __call__(self, **kwargs):
        self.n += 1
        return self.sink(**kwargs)


def run(raw_root: Path = RAW_ROOT, admin_unit_lookup=None, db_quarantine: bool = False):
    manifest_dir = raw_root / "manifests"
    quarantine_rows: list[dict] = []

    if db_quarantine:
        from pipeline.utils.quarantine import write_quarantine as sink
    else:
        def sink(**kwargs):
            quarantine_rows.append({k: kwargs.get(k) for k in
                                    ("source", "domain", "source_document", "reason_code", "message", "parser_version")})
            return True

    def art(dataset_dir, manifest, dataset, org, suffixes=None):
        return discover_artifacts(raw_root / dataset_dir, manifest_dir / manifest, dataset, org, suffixes)

    parsed_out, canonical_out, results = {}, {}, []

    def finish(name, result, parsed, canonical, parsed_name):
        results.append(result)
        parsed_out[f"{name}/{parsed_name}"] = parsed
        for domain, recs in canonical.items():
            canonical_out.setdefault((domain, name), []).extend(recs)

    # ---- SUPARCO
    a = art("suparco/disasterwatch", "suparco_disasterwatch.jsonl", "disasterwatch", "suparco")
    res, parsed, canon = _run_dataset(
        "suparco_disasterwatch", a, [(lambda x: x.filename == "campaigns-live.json", suparco.parse_campaigns)],
        lambda u, s: {"hazard_alert": adapters.adapt_suparco_campaigns(u, quarantine=s, admin_unit_lookup=admin_unit_lookup)},
        sink)
    finish("suparco", res, parsed, canon, "campaigns")

    # ---- EPA Punjab AQI (three endpoints -> one canonical domain)
    a = art("epa_punjab/aqi_punjab", "epa_punjab_aqi_punjab.jsonl", "aqi_punjab", "epa_punjab")
    epa_parsed = {"stations": [], "calendar": [], "districts": []}

    def epa_handler(kind, fn):
        def wrapped(artifact):
            recs, fails = fn(artifact)
            epa_parsed[kind].extend(recs)
            return recs, fails
        return wrapped

    handlers = [(lambda x: x.filename.startswith("district-stations"), epa_handler("stations", epa_aqi.parse_station_snapshot)),
                (lambda x: x.filename.startswith("aqi-calendar"), epa_handler("calendar", epa_aqi.parse_calendar)),
                (lambda x: x.filename == "districts.json", epa_handler("districts", epa_aqi.parse_districts))]

    def epa_adapt(unique, s):
        st = [r for r in unique if r["source_record_id"].startswith("station:")]
        cal = [r for r in unique if r["source_record_id"].startswith("aqi-calendar:")]
        return {"air_quality_observation": adapters.adapt_epa_stations(st, quarantine=s, admin_unit_lookup=admin_unit_lookup)
                + adapters.adapt_epa_calendar(cal, quarantine=s, admin_unit_lookup=admin_unit_lookup)}

    res, parsed, canon = _run_dataset("epa_punjab_aqi", a, handlers, epa_adapt, sink)
    ref = _dedupe(epa_parsed["districts"])
    from scripts.geo.canonical_data import DISTRICTS
    from scripts.geo.resolver import resolve
    statuses = Counter(resolve(r["district"], DISTRICTS).status for r in ref)
    res["reference_district_list"] = {"records": len(ref), "not_canonicalized_reason":
                                      "reference list of names, not an observation", "geo": dict(sorted(statuses.items()))}
    parsed = [r for r in parsed if not r["source_record_id"].startswith("district:")]
    finish("epa_punjab_aqi", res, parsed, canon, "aqi_observations")
    parsed_out["epa_punjab_aqi/districts"] = ref

    # ---- FFC reservoir
    a = art("ffc/reservoir_levels", "ffc_reservoir_levels.jsonl", "reservoir_levels", "ffc", (".html",))
    res, parsed, canon = _run_dataset(
        "ffc_reservoir_levels", a, [(lambda x: x.filename.startswith("homepage"), ffc_reservoir.parse_reservoir_html)],
        lambda u, s: {"reservoir_observation": adapters.adapt_ffc_reservoir(u, quarantine=s)}, sink)
    finish("ffc", res, parsed, canon, "reservoir_levels")

    # ---- FFC DFSR / GLOF
    a = art("ffc/dfsr_glof_archive", "ffc_dfsr_glof_archive.jsonl", "dfsr_glof_archive", "ffc")

    def dfsr_adapt(u, s):
        docs = [r for r in u if r["record_kind"] == "document"]
        glof = [r for r in u if r["record_kind"] == "glof_alert"]
        return {"document": adapters.adapt_documents(docs, source="ffc", dataset="dfsr_glof_archive", quarantine=s),
                "hazard_alert": adapters.adapt_glof_alerts(glof, quarantine=s, admin_unit_lookup=admin_unit_lookup)}

    res, parsed, canon = _run_dataset("ffc_dfsr_glof", a, [(lambda x: x.path.suffix.lower() == ".pdf", ffc_dfsr.parse_ffc_pdf)],
                                      dfsr_adapt, sink)
    finish("ffc", res, parsed, canon, "dfsr_glof")

    # ---- PMD / NDMC
    a = art("pmd_ndmc/bulletins", "pmd_ndmc_bulletins.jsonl", "bulletins", "pmd_ndmc")
    res, parsed, canon = _run_dataset(
        "pmd_ndmc_bulletins", a, [(lambda x: x.path.suffix.lower() == ".pdf", pmd_ndmc.parse_bulletin_pdf)],
        lambda u, s: {"document": adapters.adapt_documents(u, source="pmd_ndmc", dataset="bulletins", quarantine=s)},
        sink)
    finish("pmd_ndmc", res, parsed, canon, "bulletins")

    return {"parser_version": PARSER_VERSION, "datasets": results, "quarantine": sorted(
        quarantine_rows, key=lambda r: (r["source"], r["source_document"] or "", r["reason_code"], r["message"])),
        "parsed": parsed_out, "canonical": canonical_out}


def _write_jsonl_plain(records, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
                            for r in records), encoding="utf-8")


def write_outputs(outcome, parsed_root: Path = PARSED_ROOT, canonical_root: Path = CANONICAL_ROOT):
    for key, records in sorted(outcome["parsed"].items()):
        folder, name = key.split("/", 1)
        _write_jsonl_plain(records, parsed_root / folder / f"{name}.jsonl")
    for (domain, dataset), records in sorted(outcome["canonical"].items()):
        write_jsonl(records, canonical_root / domain / f"tier1_{dataset}.jsonl")
    _write_jsonl_plain(outcome["quarantine"], parsed_root / "quarantine.jsonl")
    report = {"parser_version": outcome["parser_version"], "datasets": outcome["datasets"],
              "records_quarantined_total": len(outcome["quarantine"])}
    (parsed_root / "coverage_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                                      encoding="utf-8")
    return report


def _try_db_lookup():
    try:
        from sqlalchemy import text

        from config.database import engine
        from pipeline.canonical.geography import build_db_admin_unit_lookup
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return build_db_admin_unit_lookup(engine)
    except Exception:
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    lookup = None if "--no-db" in argv else _try_db_lookup()
    outcome = run(admin_unit_lookup=lookup, db_quarantine="--db-quarantine" in argv)
    report = write_outputs(outcome)
    print(json.dumps({"admin_unit_lookup": "postgres(read-only)" if lookup else "none", **report}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
