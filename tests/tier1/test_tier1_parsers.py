"""Task 19 -- Tier-1 parser, canonical-adapter, idempotency and coverage tests.

Fixtures under tests/tier1/fixtures/raw are cut from the real Task 15 artifacts (JSON copied
verbatim / trimmed to a few days; PDFs are 1-2 page excerpts). Nothing here touches the database
or data/raw: geography uses an in-memory lookup and quarantine uses an in-memory sink.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import pytest

from pipeline.canonical.contracts import validate_record
from pipeline.canonical.geography import build_dict_admin_unit_lookup
from pipeline.canonical.normalization import normalize_timestamp
from pipeline.canonical import tier1_adapters as ad
from scripts.parsing.tier1 import epa_aqi, ffc_dfsr, ffc_reservoir, pmd_ndmc, suparco
from scripts.parsing.tier1.artifacts import Artifact, sha256_file
from scripts.parsing.tier1.run_tier1 import _dedupe

FIX = Path(__file__).parent / "fixtures" / "raw"
RETRIEVED = "2026-09-16T10:14:00+00:00"
LOOKUP = build_dict_admin_unit_lookup({"Lahore": 11, "Gilgit-Baltistan": 3, "Khyber Pakhtunkhwa": 4})


def art(path: Path, dataset="fixture", org="fixture", retrieved=RETRIEVED, url="https://example.invalid/x") -> Artifact:
    return Artifact(path, sha256_file(path), url, retrieved, dataset, org)


def sink_into(bucket):
    def sink(**kwargs):
        bucket.append(kwargs)
        return True
    return sink


# ---------------------------------------------------------------- SUPARCO
def test_suparco_parses_campaigns_and_derives_hazard_only_from_glide():
    recs, fails = suparco.parse_campaigns(art(FIX / "suparco" / "campaigns-live.json"))
    assert not fails and len(recs) == 2
    by_name = {r["name"]: r for r in recs}
    assert by_name["Monsoon 2026"]["hazard_type"] == "flood"           # from FL- GLIDE prefix
    assert by_name["Nepal Floods 2026"]["hazard_type"] is None          # no GLIDE number -> not inferred from the name
    assert by_name["Monsoon 2026"]["source_record_id"] == "campaign:e399b999-d882-4a5e-9b6c-fae6424e3d54"


def test_suparco_canonical_provenance_nulls_and_no_location():
    recs, _ = suparco.parse_campaigns(art(FIX / "suparco" / "campaigns-live.json"))
    quarantined = []
    canon = ad.adapt_suparco_campaigns(recs, quarantine=sink_into(quarantined), admin_unit_lookup=LOOKUP)
    assert len(canon) == 2 and not quarantined
    nepal = next(c for c in canon if c["title"] == "Nepal Floods 2026")
    assert nepal["valid_until"] is None and nepal["hazard_type"] is None
    assert nepal["admin_unit_id"] is None and nepal["location_original"] is None
    assert nepal["provenance"]["sha256"] and nepal["provenance"]["source_url_or_path"] == "https://example.invalid/x"
    assert nepal["provenance"]["parser_version"] == "tier1-parser-1.0.0"
    assert all(validate_record(c) == [] for c in canon)


def test_suparco_malformed_json_and_bad_entry_are_isolated(tmp_path):
    bad = tmp_path / "campaigns-live.json"
    bad.write_text("{not json")
    recs, fails = suparco.parse_campaigns(art(bad))
    assert recs == [] and fails[0]["reason_code"] == "malformed_json"
    good_and_bad = tmp_path / "c2.json"
    good_and_bad.write_text(json.dumps({"data": [{"id": "a", "name": "ok"}, {"id": "b"}]}))
    recs, fails = suparco.parse_campaigns(art(good_and_bad))
    assert [r["campaign_id"] for r in recs] == ["a"] and fails[0]["reason_code"] == "missing_required_field"


def test_suparco_duplicate_retrievals_collapse_to_the_earliest():
    a = suparco.parse_campaigns(art(FIX / "suparco" / "campaigns-live.json", retrieved="2026-09-16T00:00:00+00:00"))[0]
    b = suparco.parse_campaigns(art(FIX / "suparco" / "campaigns-live.json", retrieved="2026-09-15T00:00:00+00:00"))[0]
    unique = _dedupe(a + b)
    assert len(unique) == 2 and all(r["artifact"]["retrieved_at"] == "2026-09-15T00:00:00+00:00" for r in unique)


# ---------------------------------------------------------------- EPA AQI
def test_epa_station_snapshot_preserves_nulls_and_labels_observation_time():
    recs, fails = epa_aqi.parse_station_snapshot(art(FIX / "epa" / "district-stations-lahore.json"))
    assert not fails and len(recs) == 10
    safari = next(r for r in recs if r["station_name"] == "Safari Park")
    assert safari["pm25"] is None and safari["pm10"] == "190.90"
    assert safari["observed_at"] == RETRIEVED and safari["observed_at_basis"] == "retrieved_at"


def test_epa_canonical_numeric_coercion_null_not_zero_and_geography():
    recs, _ = epa_aqi.parse_station_snapshot(art(FIX / "epa" / "district-stations-lahore.json"))
    canon = ad.adapt_epa_stations(recs, quarantine=sink_into([]), admin_unit_lookup=LOOKUP)
    safari = next(c for c in canon if c["station_name"] == "Safari Park")
    assert safari["pm25"] is None                       # a missing pollutant is never 0
    assert safari["pm10"] == 190.9 and isinstance(safari["aqi"], int)
    assert safari["resolution_status"] == "resolved" and safari["admin_unit_id"] == 11 and safari["district"] == "Lahore"
    assert safari["category"] is None and safari["city"] is None   # never inferred
    assert all(validate_record(c) == [] for c in canon)


def test_epa_calendar_parses_daily_city_aqi():
    recs, fails = epa_aqi.parse_calendar(art(FIX / "epa" / "aqi-calendar-lahore.json"))
    assert not fails and [r["date"] for r in recs] == ["2026-09-14", "2026-09-15"]
    canon = ad.adapt_epa_calendar(recs, quarantine=sink_into([]), admin_unit_lookup=LOOKUP)
    assert canon[0]["observed_at"] == "2026-09-14"      # date-only stays date-only (no invented midnight)
    assert canon[0]["station_name"] is None and canon[0]["pm25"] is None


def test_epa_non_numeric_aqi_becomes_null_never_zero():
    recs, _ = epa_aqi.parse_station_snapshot(art(FIX / "epa" / "district-stations-lahore.json"))
    recs[0]["aqi"] = "not-a-number"
    q = []
    canon = ad.adapt_epa_stations(recs[:1], quarantine=sink_into(q), admin_unit_lookup=LOOKUP)
    assert canon[0]["aqi"] is None                       # coerced to null, never guessed
    assert q == []                                       # null is valid; the value is preserved as unknown, not zero


def test_epa_ambiguous_and_unresolved_districts():
    rec = epa_aqi.parse_station_snapshot(art(FIX / "epa" / "district-stations-lahore.json"))[0][:1]
    rec[0]["district"] = "Lahore, Kasur"
    amb = ad.adapt_epa_stations(rec, quarantine=sink_into([]), admin_unit_lookup=LOOKUP)[0]
    assert amb["resolution_status"] == "ambiguous" and amb["admin_unit_id"] is None and amb["district"] is None
    rec[0]["district"] = "Atlantis"
    unres = ad.adapt_epa_stations(rec, quarantine=sink_into([]), admin_unit_lookup=LOOKUP)[0]
    assert unres["resolution_status"] == "unresolved" and unres["location_original"] == "Atlantis"


def test_epa_districts_reference_and_malformed_structure(tmp_path):
    recs, fails = epa_aqi.parse_districts(art(FIX / "epa" / "districts.json"))
    assert len(recs) == 37 and not fails
    bad = tmp_path / "districts.json"
    bad.write_text(json.dumps({"success": True}))
    assert epa_aqi.parse_districts(art(bad))[1][0]["reason_code"] == "unexpected_structure"


# ---------------------------------------------------------------- FFC reservoir
def test_ffc_reservoir_measurements_units_and_source_spelling():
    recs, fails = ffc_reservoir.parse_reservoir_html(art(FIX / "ffc" / "homepage.html"))
    assert not fails and {r["reservoir_name"] for r in recs} == {"Tarbela", "Mangla", "Chashma"}
    tarbela = next(r for r in recs if r["reservoir_name"] == "Tarbela")
    assert tarbela["reservoir_name_original"] == "Tarble"          # source typo preserved
    assert tarbela["observed_at"] == "2026-09-16T06:00:00"
    canon = ad.adapt_ffc_reservoir(recs, quarantine=sink_into([]))
    t = next(c for c in canon if c["reservoir_name"] == "Tarbela")
    assert t["water_level"] == 1542.04 and t["unit"] == "ft" and t["live_storage"] == 5.122 and t["storage_unit"] == "MAF"
    assert t["resolution_status"] == "not_attempted" and t["admin_unit_id"] is None   # 'Mangla' must not match a district
    assert all(validate_record(c) == [] for c in canon)


def test_ffc_reservoir_page_without_the_sentence_is_a_failure(tmp_path):
    page = tmp_path / "homepage.html"
    page.write_text("<html><body>nothing here</body></html>")
    recs, fails = ffc_reservoir.parse_reservoir_html(art(page))
    assert recs == [] and fails[0]["reason_code"] == "reservoir_sentence_not_found"


def test_reservoir_unit_violation_is_rejected_by_the_contract():
    recs, _ = ffc_reservoir.parse_reservoir_html(art(FIX / "ffc" / "homepage.html"))
    recs[0]["water_level_unit"] = "m"
    q = []
    ad.adapt_ffc_reservoir(recs[:1], quarantine=sink_into(q))
    assert q and "invalid_unit_water_level" in q[0]["message"]


# ---------------------------------------------------------------- FFC DFSR / GLOF
def test_dfsr_report_date_and_narrative_preserved():
    recs, fails = ffc_dfsr.parse_ffc_pdf(art(FIX / "ffc" / "DFSR-01-07-2026.pdf"))
    assert not fails and len(recs) == 1
    doc = recs[0]
    assert doc["doc_type"] == "dfsr" and doc["report_date"] == "2026-07-01" and doc["hazard_topic"] == "flood"
    assert "Federal Flood" in doc["text"] and doc["text_char_count"] == len(doc["text"])
    canon = ad.adapt_documents(recs, source="ffc", dataset="dfsr_glof_archive", quarantine=sink_into([]))
    assert canon[0]["domain"] == "document" and canon[0]["report_date"] == "2026-07-01"
    assert canon[0]["provenance"]["source_file"].endswith("DFSR-01-07-2026.pdf")


def test_glof_alert_emits_document_and_one_alert_per_named_province():
    recs, fails = ffc_dfsr.parse_ffc_pdf(art(FIX / "ffc" / "Glof-Alert.pdf"))
    assert not fails
    doc = next(r for r in recs if r["record_kind"] == "document")
    assert doc["issued_at"] == "2026-06-27T09:00:00"
    alerts = [r for r in recs if r["record_kind"] == "glof_alert"]
    assert sorted(a["affected_area"] for a in alerts) == ["Gilgit-Baltistan", "Khyber Pakhtunkhwa"]
    canon = ad.adapt_glof_alerts(alerts, quarantine=sink_into([]), admin_unit_lookup=LOOKUP)
    assert {c["admin_unit_id"] for c in canon} == {3, 4} and all(c["hazard_type"] == "glof" for c in canon)
    assert all(c["severity"] is None for c in canon)     # severity never invented


def test_image_only_pdf_is_a_no_text_layer_failure_not_a_record(tmp_path):
    scan = tmp_path / "Press-Release-test.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(scan)
    recs, fails = ffc_dfsr.parse_ffc_pdf(art(scan))
    assert recs == [] and fails[0]["reason_code"] == "no_text_layer"


def test_corrupt_pdf_is_isolated():
    recs, fails = ffc_dfsr.parse_ffc_pdf(art(FIX / "pmd" / "corrupt.pdf"))
    assert recs == [] and fails[0]["reason_code"] == "pdf_unreadable"


# ---------------------------------------------------------------- PMD / NDMC
def test_ndmc_bulletin_title_period_and_no_invented_publication_date():
    recs, fails = pmd_ndmc.parse_bulletin_pdf(art(FIX / "pmd" / "1.pdf"))
    assert not fails
    b = recs[0]
    assert b["title"] == "FORTNIGHTLY DROUGHT BULLETIN"
    assert (b["period_start"], b["period_end"]) == ("2026-01-01", "2026-01-15")
    assert b["publication_date"] is None     # never invented (the excerpt fixture carries no PDF metadata)
    canon = ad.adapt_documents(recs, source="pmd_ndmc", dataset="bulletins", quarantine=sink_into([]))
    assert canon[0]["publication_date"] is None and canon[0]["hazard_topic"] == "drought"
    assert "National Drought Monitoring" in canon[0]["text"]


def test_ndmc_bulletin_without_a_title_heading_keeps_title_null():
    recs, _ = pmd_ndmc.parse_bulletin_pdf(art(FIX / "pmd" / "10.pdf"))
    assert recs[0]["title"] is None and recs[0]["period_start"] is None and recs[0]["heading_lines"]


# ---------------------------------------------------------------- canonical / normalization / idempotency
def test_date_only_timestamp_stays_date_only():
    assert normalize_timestamp("2026-09-17") == "2026-09-17"
    assert normalize_timestamp("2026-09-17T06:00:00") == "2026-09-17T06:00:00"
    assert normalize_timestamp("2026-13-45") is None


def test_document_without_provenance_is_quarantined():
    recs, _ = pmd_ndmc.parse_bulletin_pdf(art(FIX / "pmd" / "1.pdf", retrieved=None))
    q = []
    assert ad.adapt_documents(recs, source="pmd_ndmc", dataset="bulletins", quarantine=sink_into(q)) == []
    assert "missing_ingestion_timestamp" in q[0]["message"]


def test_parsing_and_adapting_twice_is_identical():
    def once():
        recs = epa_aqi.parse_station_snapshot(art(FIX / "epa" / "district-stations-lahore.json"))[0]
        return json.dumps(ad.adapt_epa_stations(recs, quarantine=sink_into([]), admin_unit_lookup=LOOKUP), sort_keys=True)
    assert once() == once()


def test_run_tier1_is_idempotent_and_never_writes_raw(tmp_path):
    from scripts.parsing.tier1 import run_tier1

    raw = tmp_path / "raw"
    (raw / "manifests").mkdir(parents=True)
    (raw / "suparco" / "disasterwatch").mkdir(parents=True)
    content = (FIX / "suparco" / "campaigns-live.json").read_bytes()
    (raw / "suparco" / "disasterwatch" / "campaigns-live.json").write_bytes(content)
    (raw / "manifests" / "suparco_disasterwatch.jsonl").write_text(json.dumps(
        {"sha256": hashlib.sha256(content).hexdigest(), "retrieved_at": RETRIEVED, "source_url": "https://example.invalid/c"}) + "\n")
    for name in ("epa_punjab/aqi_punjab", "ffc/reservoir_levels", "ffc/dfsr_glof_archive", "pmd_ndmc/bulletins"):
        (raw / name).mkdir(parents=True)
    before = {p: p.read_bytes() for p in raw.rglob("*") if p.is_file()}

    def go(out):
        outcome = run_tier1.run(raw_root=raw)
        run_tier1.write_outputs(outcome, out / "parsed", out / "canonical")
        return {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}

    first, second = go(tmp_path / "o1"), go(tmp_path / "o2")
    assert first == second and first
    assert {p: p.read_bytes() for p in raw.rglob("*") if p.is_file()} == before
    report = json.loads(first[Path("parsed/coverage_report.json")])
    suparco_row = next(d for d in report["datasets"] if d["dataset"] == "suparco_disasterwatch")
    assert suparco_row["records_canonicalized"] == 2 and suparco_row["raw_files_found"] == 1


@pytest.mark.parametrize("domain", ["air_quality_observation", "reservoir_observation", "document", "hazard_alert"])
def test_spark_schema_registered_for_each_tier1_domain(domain):
    try:
        from databricks.src.common.schemas import DOMAIN_SCHEMAS
        from databricks.src.silver.canonical_silver import _TIMESTAMP_COLUMNS
    except ModuleNotFoundError:
        pytest.skip("databricks/ is not mounted in this environment (Docker volume-mount limitation)")
    assert domain in DOMAIN_SCHEMAS and domain in _TIMESTAMP_COLUMNS
