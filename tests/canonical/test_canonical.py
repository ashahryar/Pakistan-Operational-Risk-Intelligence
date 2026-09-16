from pathlib import Path

from pipeline.canonical.adapters import adapt_ndma, adapt_pdma_gauge, adapt_pdma_rainfall, adapt_pmd_alerts, adapt_pmd_daily, adapt_pmd_weekly
from pipeline.canonical.contracts import validate_record
from pipeline.canonical.normalization import normalize_number, normalize_string, normalize_timestamp, normalize_unit
from pipeline.canonical.output import write_jsonl


INGESTED = "2026-09-16T12:00:00+00:00"


def test_normalizers_preserve_unknowns_and_do_not_claim_utc():
    assert normalize_string("  Lahore\n Station ") == "Lahore Station"
    assert normalize_number("1,250") == 1250
    assert normalize_number("N/A") is None
    assert normalize_number("twelve") is None
    assert normalize_timestamp("05 September 2026") == "2026-09-05"
    assert normalize_timestamp("2026-09-05T12:00:00") == "2026-09-05T12:00:00"
    assert normalize_unit("millimeters") == "mm"
    assert normalize_unit("metres", {"mm", "ft"}) is None


def test_pdma_adapters_and_geography_statuses():
    rainfall = adapt_pdma_rainfall({"source_file": "rain.pdf", "created_at": INGESTED, "report_date": "02.07.2026", "stations": [{"station": "Lahore", "rainfall_mm": "12.5"}]})
    assert rainfall[0]["rainfall_amount"] == 12.5
    assert rainfall[0]["resolution_status"] == "resolved"
    assert rainfall[0]["admin_unit_id"] is None
    ambiguous = adapt_pdma_rainfall({"source_file": "rain.pdf", "created_at": INGESTED, "report_date": "02.07.2026", "stations": [{"station": "Lahore, Multan", "rainfall_mm": 1}]})
    assert ambiguous[0]["resolution_status"] == "ambiguous"
    unresolved = adapt_pdma_gauge({"source_file": "gauge.pdf", "created_at": INGESTED, "report_datetime": "2026-07-02T12:00:00", "gauges": [{"station": "Unknown Place", "river": "Indus", "current_level_ft": "4", "discharge_cusecs": "1,250"}]})
    assert unresolved[0]["resolution_status"] == "unresolved"
    assert unresolved[0]["discharge"] == 1250


def test_ndma_and_pmd_adapters_preserve_provenance_and_nulls():
    ndma = adapt_ndma({"filename": "sitrep.pdf", "report_number": "72", "report_date": "5 September 2026", "parsed_at": INGESTED, "casualties": [{"province": "Punjab", "deaths": "0", "injured": None}]})
    assert ndma[0]["deaths"] == 0 and ndma[0]["injured"] is None
    assert ndma[0]["provenance"]["source_document"] == "sitrep.pdf"
    daily = adapt_pmd_daily([{"city": "Lahore", "scraped_at": INGESTED, "max_temperature": "32", "humidity": "60", "day1": "Hot"}], ingestion_timestamp=INGESTED)
    assert daily[0]["temperature"] == 32
    alerts = adapt_pmd_alerts({"regions": ["Punjab"], "alert_type": "Rain", "forecast": "Heavy rainfall", "scraped_at": INGESTED}, ingestion_timestamp=INGESTED)
    assert alerts[0]["hazard_type"] == "Rain"
    weekly = adapt_pmd_weekly([{"regions": ["Punjab"], "scraped_at": INGESTED, "date": "2026-09-17", "weather_summary": "Rain"}], ingestion_timestamp=INGESTED)
    assert weekly[0]["hazard_type"] == "weather_outlook"


def test_contract_rejection_quarantines_and_output_is_idempotent(tmp_path: Path):
    calls = []
    bad = adapt_pdma_rainfall({"source_file": "rain.pdf", "created_at": INGESTED, "stations": [{"station": "Lahore", "rainfall_mm": "not numeric"}]}, quarantine=lambda **kwargs: calls.append(kwargs) or True)
    assert bad == [] and calls[0]["reason_code"] == "canonical_invalid"
    assert "missing_source" in validate_record({"domain": "rainfall_observation"})
    records = adapt_pdma_rainfall({"source_file": "rain.pdf", "created_at": INGESTED, "stations": [{"station": "Lahore", "rainfall_mm": 1}]})
    target = tmp_path / "canonical" / "rainfall.jsonl"
    assert write_jsonl(records, target).read_bytes() == write_jsonl(records, target).read_bytes()
