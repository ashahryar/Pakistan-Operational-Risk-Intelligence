"""Task 21 -- Gold registry and transform tests. Uses small, clearly-synthetic canonical-shaped
fixtures for edge cases (missing data, unresolved geography, duplicates), plus one real-fixture
check against the actual Task 20 Tier-1 reservoir output when present. No pyspark required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.gold import transforms as gt
from pipeline.gold.domain_registry import GOLD_REGISTRY, assert_gold_sources_exist_in_silver_registry

REPO_ROOT = Path(__file__).resolve().parents[2]


def _prov(source="pdma", rid="r1", ts="2026-09-01T00:00:00+00:00"):
    return {"source_organization": source.upper(), "source_dataset": "x", "parser_version": "1.0.0",
            "normalization_version": "1.0.0"}


# ---------------------------------------------------------------- registry
def test_gold_registry_sources_exist_in_silver_domain_registry():
    assert assert_gold_sources_exist_in_silver_registry() == []


def test_every_gold_dataset_has_a_non_empty_business_key():
    for name, spec in GOLD_REGISTRY.items():
        assert spec.business_key, f"{name} has no business key"


def test_gold_registry_states_no_risk_score_is_computed():
    spec = GOLD_REGISTRY["gold_operational_risk_inputs"]
    assert "NO numeric risk score" in spec.aggregation_rule
    for forbidden in ("risk_score", "probability", "composite_index"):
        assert forbidden not in spec.optional_fields and forbidden not in spec.required_fields


# ---------------------------------------------------------------- weather
def test_gold_weather_daily_aggregates_same_geography_and_date_and_preserves_missing_as_null():
    records = [
        {"source": "pmd", "source_record_id": "w1", "ingestion_timestamp": "2026-08-12T00:00:16+00:00",
         "observed_at": "2026-08-12T00:00:16+00:00", "resolution_status": "resolved", "admin_unit_key": "Lahore",
         "admin_unit_id": 11, "district": "Lahore", "location_original": "Lahore", "temperature": 30.0,
         "humidity": 50.0, "weather_condition": None, "precipitation": None, "wind_speed": None},
        {"source": "pmd", "source_record_id": "w2", "ingestion_timestamp": "2026-08-12T00:00:16+00:00",
         "observed_at": "2026-08-12T06:00:00+00:00", "resolution_status": "resolved", "admin_unit_key": "Lahore",
         "admin_unit_id": 11, "district": "Lahore", "location_original": "Lahore", "temperature": 34.0,
         "humidity": None, "weather_condition": None, "precipitation": None, "wind_speed": None},
    ]
    out = gt.build_gold_weather_daily(records)
    assert len(out) == 1
    row = out[0]
    assert row["date"] == "2026-08-12" and row["observation_count"] == 2
    assert row["temperature_avg"] == 32.0 and row["temperature_min"] == 30.0 and row["temperature_max"] == 34.0
    assert row["humidity_avg"] == 50.0           # the single non-null value, not averaged with a fabricated 0
    assert row["admin_unit_id"] == 11


def test_gold_weather_daily_unresolved_geography_keeps_original_text_and_no_admin_unit():
    records = [{"source": "pmd", "source_record_id": "w3", "ingestion_timestamp": "2026-08-12T00:00:16+00:00",
               "observed_at": "2026-08-12T00:00:16+00:00", "resolution_status": "unresolved", "admin_unit_key": None,
               "admin_unit_id": None, "district": None, "location_original": "Nonexistentabad", "temperature": 28.0,
               "humidity": None, "weather_condition": None, "precipitation": None, "wind_speed": None}]
    row = gt.build_gold_weather_daily(records)[0]
    assert row["admin_unit_id"] is None and row["geography_key"] == "unresolved:Nonexistentabad"
    assert row["resolution_status"] == "unresolved"


def test_gold_weather_daily_all_metrics_missing_stays_null_not_zero():
    records = [{"source": "pmd", "source_record_id": "w4", "ingestion_timestamp": "2026-08-12T00:00:16+00:00",
               "observed_at": "2026-08-12T00:00:16+00:00", "resolution_status": "resolved", "admin_unit_key": "Lahore",
               "admin_unit_id": 11, "district": "Lahore", "location_original": "Lahore", "temperature": None,
               "humidity": None, "weather_condition": None, "precipitation": None, "wind_speed": None}]
    row = gt.build_gold_weather_daily(records)[0]
    assert row["temperature_avg"] is None and row["temperature_min"] is None  # never fabricated as 0.0


# ---------------------------------------------------------------- rainfall
def test_gold_rainfall_daily_sums_same_station_and_day():
    records = [
        {"source": "pdma", "source_record_id": "r1", "ingestion_timestamp": "t1", "observed_at": "2026-07-01",
         "resolution_status": "resolved", "admin_unit_key": "Layyah", "admin_unit_id": 5, "district": "Layyah",
         "location_original": "Layyah", "station_name": "Layyah", "rainfall_amount": 10.0, "unit": "mm"},
        {"source": "pdma", "source_record_id": "r2", "ingestion_timestamp": "t2", "observed_at": "2026-07-01",
         "resolution_status": "resolved", "admin_unit_key": "Layyah", "admin_unit_id": 5, "district": "Layyah",
         "location_original": "Layyah", "station_name": "Layyah", "rainfall_amount": 5.0, "unit": "mm"},
    ]
    row = gt.build_gold_rainfall_daily(records)[0]
    assert row["rainfall_total"] == 15.0 and row["rainfall_avg"] == 7.5 and row["observation_count"] == 2


def test_gold_rainfall_daily_preserves_station_identity_not_collapsed_into_district():
    records = [
        {"source": "pdma", "source_record_id": "r3", "ingestion_timestamp": "t1", "observed_at": "2026-07-01",
         "resolution_status": "resolved", "admin_unit_key": "Multan", "admin_unit_id": 7, "district": "Multan",
         "location_original": "Station A", "station_name": "Station A", "rainfall_amount": 1.0, "unit": "mm"},
        {"source": "pdma", "source_record_id": "r4", "ingestion_timestamp": "t1", "observed_at": "2026-07-01",
         "resolution_status": "resolved", "admin_unit_key": "Multan", "admin_unit_id": 7, "district": "Multan",
         "location_original": "Station B", "station_name": "Station B", "rainfall_amount": 2.0, "unit": "mm"},
    ]
    out = gt.build_gold_rainfall_daily(records)
    assert len(out) == 2 and {r["station_name"] for r in out} == {"Station A", "Station B"}


# ---------------------------------------------------------------- gauge
def test_gold_gauge_daily_unresolved_station_never_gets_a_fabricated_district():
    records = [{"source": "pdma", "source_record_id": "g1", "ingestion_timestamp": "t1", "observed_at": "2026-07-01T12:00:00",
               "resolution_status": "unresolved", "admin_unit_key": None, "admin_unit_id": None, "district": None,
               "location_original": "Tarbela", "station_name": "Tarbela", "river_name": "Indus",
               "water_level": 1542.0, "discharge": None}]
    row = gt.build_gold_gauge_daily(records)[0]
    assert row["admin_unit_id"] is None and row["district"] is None and row["resolution_status"] == "unresolved"
    assert row["water_level_avg"] == 1542.0


def test_gold_gauge_daily_min_max_mean_over_same_station_day():
    records = [
        {"source": "pdma", "source_record_id": "g2", "ingestion_timestamp": "t1", "observed_at": "2026-07-01T06:00:00",
         "resolution_status": "unresolved", "admin_unit_key": None, "admin_unit_id": None, "district": None,
         "location_original": "Chashma", "station_name": "Chashma", "river_name": "Indus", "water_level": 640.0, "discharge": 1000.0},
        {"source": "pdma", "source_record_id": "g3", "ingestion_timestamp": "t1", "observed_at": "2026-07-01T18:00:00",
         "resolution_status": "unresolved", "admin_unit_key": None, "admin_unit_id": None, "district": None,
         "location_original": "Chashma", "station_name": "Chashma", "river_name": "Indus", "water_level": 650.0, "discharge": 1200.0},
    ]
    row = gt.build_gold_gauge_daily(records)[0]
    assert row["water_level_min"] == 640.0 and row["water_level_max"] == 650.0 and row["water_level_avg"] == 645.0
    assert row["discharge_min"] == 1000.0 and row["discharge_max"] == 1200.0


# ---------------------------------------------------------------- air quality
def test_gold_air_quality_keeps_station_snapshot_and_daily_calendar_as_separate_grains():
    records = [
        {"source": "epa_punjab", "source_record_id": "a1", "ingestion_timestamp": "t1", "observed_at": "2026-09-16T10:00:00",
         "observed_at_basis": "retrieved_at", "granularity": "station_snapshot", "resolution_status": "resolved",
         "admin_unit_key": "Lahore", "admin_unit_id": 11, "district": "Lahore", "location_original": "Lahore",
         "station_name": "Wagha Border", "aqi": 200, "pm25": None, "pm10": 100.0, "no2": None, "so2": None, "co": None, "o3": None},
        {"source": "epa_punjab", "source_record_id": "a2", "ingestion_timestamp": "t1", "observed_at": "2026-09-16",
         "observed_at_basis": "calendar_date", "granularity": "daily_district", "resolution_status": "resolved",
         "admin_unit_key": "Lahore", "admin_unit_id": 11, "district": "Lahore", "location_original": "Lahore",
         "station_name": None, "aqi": 170, "pm25": None, "pm10": None, "no2": None, "so2": None, "co": None, "o3": None},
    ]
    out = gt.build_gold_air_quality(records)
    assert len(out) == 2
    granularities = {r["granularity"] for r in out}
    assert granularities == {"station_snapshot", "daily_district"}
    station_row = next(r for r in out if r["granularity"] == "station_snapshot")
    assert station_row["observation_time_basis"] == "retrieved_at"
    assert station_row["pm25_avg"] is None       # missing pollutant never becomes 0


# ---------------------------------------------------------------- pass-through (disaster/alerts/reservoir/documents)
def test_gold_disaster_events_does_not_aggregate_away_individual_events():
    records = [
        {"source": "ndma", "source_record_id": "e1", "ingestion_timestamp": "t1", "event_type": "sitrep",
         "event_name": None, "event_date": "2026-06-27", "resolution_status": "resolved", "admin_unit_id": 1,
         "province": "Punjab", "district": None, "location_original": "Punjab", "deaths": 2, "injured": None,
         "affected_population": None, "houses_damaged": None, "roads_damaged": None, "bridges_damaged": None,
         "rescued": None, "evacuated": None, "provenance": _prov()},
        {"source": "ndma", "source_record_id": "e2", "ingestion_timestamp": "t1", "event_type": "sitrep",
         "event_name": None, "event_date": "2026-06-27", "resolution_status": "resolved", "admin_unit_id": 1,
         "province": "Punjab", "district": None, "location_original": "Punjab", "deaths": 0, "injured": None,
         "affected_population": None, "houses_damaged": None, "roads_damaged": None, "bridges_damaged": None,
         "rescued": None, "evacuated": None, "provenance": _prov()},
    ]
    out = gt.build_gold_disaster_events(records)
    assert len(out) == 2  # same geography+date, but NOT merged -- each source event stays distinct
    assert {r["deaths"] for r in out} == {2, 0}   # the real zero is preserved, not dropped


def test_gold_disaster_events_bronze_dedup_still_applies_to_true_duplicates():
    rec = {"source": "ndma", "source_record_id": "e3", "ingestion_timestamp": "t1", "event_type": "sitrep",
          "event_name": None, "event_date": "2026-06-27", "resolution_status": "resolved", "admin_unit_id": 1,
          "province": "Punjab", "district": None, "location_original": "Punjab", "deaths": 1, "injured": None,
          "affected_population": None, "houses_damaged": None, "roads_damaged": None, "bridges_damaged": None,
          "rescued": None, "evacuated": None, "provenance": _prov()}
    out = gt.build_gold_disaster_events([dict(rec, domain="disaster_event"), dict(rec, domain="disaster_event")])
    assert len(out) == 1


def test_gold_reservoir_status_never_attempts_geography():
    records = [{"source": "ffc", "source_record_id": "res1", "reservoir_name": "Mangla", "observed_at": "2026-09-16T06:00:00",
               "water_level": 1219.3, "live_storage": 5.534, "combined_live_storage": 10.873, "provenance": _prov()}]
    row = gt.build_gold_reservoir_status(records)[0]
    assert row["admin_unit_id"] is None and row["resolution_status"] == "not_attempted"


def test_gold_documents_effective_date_prefers_report_date_and_states_its_basis():
    records = [{"source": "ffc", "source_record_id": "d1", "doc_type": "dfsr", "title": "Daily Weather & Flood Situation Report",
               "report_date": "2026-07-01", "publication_date": None, "issued_at": None, "period_start": None,
               "issuing_organization": "FFC", "hazard_topic": "flood",
               "provenance": {**_prov(), "source_file": "x.pdf", "sha256": "abc", "retrieved_at": "t"}}]
    row = gt.build_gold_documents(records)[0]
    assert row["effective_date"] == "2026-07-01" and row["effective_date_basis"] == "report_date"


def test_gold_documents_no_date_anywhere_stays_null_not_fabricated():
    records = [{"source": "pmd_ndmc", "source_record_id": "d2", "doc_type": "ndmc_bulletin", "title": None,
               "report_date": None, "publication_date": None, "issued_at": None, "period_start": None,
               "issuing_organization": "NDMC", "hazard_topic": "drought",
               "provenance": {**_prov(), "source_file": "y.pdf", "sha256": "def", "retrieved_at": "t"}}]
    row = gt.build_gold_documents(records)[0]
    assert row["effective_date"] is None and row["effective_date_basis"] is None


# ---------------------------------------------------------------- operational risk inputs
def test_operational_risk_inputs_only_aligns_resolved_geography():
    rainfall = [{"source": "pdma", "source_record_id": "x1", "ingestion_timestamp": "t", "observed_at": "2026-07-01",
                "resolution_status": "unresolved", "admin_unit_id": None, "rainfall_amount": 50.0}]
    empty = []
    out = gt.build_gold_operational_risk_inputs(rainfall, empty, empty, empty, empty, empty)
    assert out == []  # an unresolved rainfall record must never create a fake geography cell


def test_operational_risk_inputs_missing_signal_stays_null_not_zero():
    rainfall = [{"source": "pdma", "source_record_id": "x2", "ingestion_timestamp": "t", "observed_at": "2026-07-01",
                "resolution_status": "resolved", "admin_unit_id": 5, "rainfall_amount": 20.0}]
    empty = []
    out = gt.build_gold_operational_risk_inputs(rainfall, empty, empty, empty, empty, empty)
    assert len(out) == 1
    row = out[0]
    assert row["rainfall_total"] == 20.0
    assert row["gauge_discharge_avg"] is None and row["aqi_avg"] is None and row["temperature_avg"] is None
    assert row["active_hazard_alert_count"] == 0  # a real documented exception: alert/event counts default
    # to 0 (an absence of alerts/events is a real, countable fact), unlike every averaged measurement signal.
    assert "rainfall_observation" in row["coverage"] and "gauge_observation" not in row["coverage"]


def test_operational_risk_inputs_never_contains_a_risk_score_field():
    rainfall = [{"source": "pdma", "source_record_id": "x3", "ingestion_timestamp": "t", "observed_at": "2026-07-01",
                "resolution_status": "resolved", "admin_unit_id": 5, "rainfall_amount": 20.0}]
    row = gt.build_gold_operational_risk_inputs(rainfall, [], [], [], [], [])[0]
    for forbidden in ("risk_score", "risk_level", "probability", "severity_score", "composite_index"):
        assert forbidden not in row


def test_operational_risk_inputs_idempotent():
    rainfall = [{"source": "pdma", "source_record_id": "x4", "ingestion_timestamp": "t", "observed_at": "2026-07-01",
                "resolution_status": "resolved", "admin_unit_id": 5, "rainfall_amount": 20.0}]
    first = gt.build_gold_operational_risk_inputs(rainfall, [], [], [], [], [])
    second = gt.build_gold_operational_risk_inputs(rainfall, [], [], [], [], [])
    assert first == second


# ---------------------------------------------------------------- real-data fixture check
def test_gold_reservoir_status_against_real_task19_canonical_output_if_present():
    path = REPO_ROOT / "data" / "parsed" / "canonical" / "reservoir_observation" / "tier1_ffc.jsonl"
    if not path.exists():
        pytest.skip("data/parsed/canonical/ not generated in this environment")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = gt.build_gold_reservoir_status(records)
    assert len(out) == len(records)  # Tarbela/Mangla/Chashma x 2 dates, no duplicates to begin with
    assert all(r["admin_unit_id"] is None for r in out)
