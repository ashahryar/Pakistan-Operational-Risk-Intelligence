# Gold / analytics foundation — status (Task 21)

**The Gold layer does not calculate operational risk scores.** No function anywhere in `pipeline/gold/` produces a probability, severity score, or composite hazard index. `gold_operational_risk_inputs` aligns raw signals by geography and date for a future, separate ML/risk-engine task to consume — it is an input layer, not a model.

## Architecture

```
Silver (Task 18-20, validated)
  ↓  pipeline/gold/transforms.py  (pure Python; reuses databricks.src.common.local_validation.bronze_dedupe)
Gold  (data/analytics/gold/datasets/*.jsonl)
  ↓
future: ML / FastAPI / Streamlit / maps / RAG / agents  (NOT this task)
```

Registry: `pipeline/gold/domain_registry.py::GOLD_REGISTRY`, cross-checked against `pipeline/canonical/domain_registry.py::DOMAIN_REGISTRY` by `assert_gold_sources_exist_in_silver_registry()` (tested in `tests/gold/test_gold_transforms.py`). No second canonical/Bronze/Silver architecture was created — every Gold transform consumes exactly the canonical JSONL fields already validated in Task 17-20, and every row is first passed through the real Task 18/20 Bronze dedup identity (`domain, source, source_record_id`, latest `ingestion_timestamp` wins) before any Gold-level aggregation.

## Datasets, grain and keys

| Dataset | Grain | Business key | Geography |
|---|---|---|---|
| `gold_weather_daily` | geography × date | `(geography_key, date)` | district, or `unresolved:<original text>` |
| `gold_rainfall_daily` | station × date | `(station_name, date)` | district carried as enrichment only — station identity never collapsed into district |
| `gold_gauge_daily` | station × date | `(station_name, date)` | district only when actually resolved |
| `gold_air_quality` | geography × date × granularity | `(geography_key, date, granularity)` | district; station-snapshot and daily-calendar kept as separate rows (different grains) |
| `gold_disaster_events` | one event (pass-through) | `(source, event_id)` | province |
| `gold_hazard_alerts` | one alert (pass-through) | `(source, alert_id)` | province |
| `gold_reservoir_status` | reservoir × time (pass-through) | `(reservoir_name, observed_at)` | **none — intentionally not attempted** |
| `gold_documents` | one document (pass-through) | `(source, document_id)` | none |
| `gold_operational_risk_inputs` | **resolved** geography × date | `(admin_unit_id, date)` | only rows with a real `admin_unit_id`; unresolved signals are never aligned |

## Geography handling

Reuses the Task 10/18 resolver and `geo.admin_unit`/`geo.name_alias` unchanged — no new table, no new resolver. `admin_unit_id` is populated only when `resolution_status == "resolved"`; every Gold row otherwise keeps `admin_unit_id = None` and the original source text in `location_original`/`geography_key`. `gold_gauge_daily` and `gold_rainfall_daily` never force a station into a district — the station/location name is always the grouping key, geography is an enrichment column.

## Temporal handling

Every Gold row carries `observation_time_basis`:
- `source_observed` — the source's own stated date/time (weather/rainfall/gauge/disaster/alert/reservoir).
- `retrieved_at` / `calendar_date` — `gold_air_quality` carries through the Task 19-established per-record `observed_at_basis` exactly, since EPA station snapshots genuinely have no measurement timestamp.
- `gold_documents`' `effective_date_basis` names which field actually supplied the date (`report_date` → `publication_date` → `issued_at` → `period_start`, first populated wins); a document with none of those keeps `effective_date = None` rather than falling back to PDF metadata (`pdf_creation_date` is not a publication claim).

No timezone is ever invented; no missing date is ever filled in.

## Derived metrics (mathematically justified only)

`rainfall_total`/`rainfall_avg` (sum/mean of same station+day observations), gauge `*_min/max/avg`, weather `*_avg/min/max`, AQI `*_avg`, `observation_count`. Nothing beyond same-key aggregation — no risk/probability/index of any kind.

## `gold_operational_risk_inputs` design

Aligns `rainfall_total`, `gauge_discharge_avg`, `gauge_water_level_avg`, `aqi_avg`, `temperature_avg`, `active_hazard_alert_count`, `disaster_event_count` by `(admin_unit_id, date)` — **only** for records whose geography actually resolved. A `coverage` dict on each row records which domains contributed; a signal absent from `coverage` is `None`, never `0` (the two count fields, `active_hazard_alert_count`/`disaster_event_count`, are a documented, deliberate exception: a true absence of alerts/events for a geography/date is itself a real, countable fact — 0 — unlike a missing *measurement*, which must stay unknown/`None`). This dataset computes no score.

## Real-data execution results (this task's run)

Regenerate with:
```
python scripts/parsing/run_task17_canonical.py
python scripts/parsing/tier1/run_tier1.py
python scripts/gold/run_gold.py
```

| Dataset | Input | Output | Duplicate keys | Geography |
|---|---:|---:|---:|---|
| gold_weather_daily | 39 | 39 | 0 | 27 resolved, 12 unresolved |
| gold_rainfall_daily | 869 | 869 | 0 | 660 resolved, 61 ambiguous, 148 unresolved |
| gold_gauge_daily | 14500 | 3686 | 0 | 93 resolved, 3593 unresolved |
| gold_air_quality | 371 | 352 | 0 | 352 resolved |
| gold_disaster_events | 1565 | 1543 | 0 | 1543 resolved |
| gold_hazard_alerts | 38 | 38 | 0 | 36 resolved, 2 unresolved |
| gold_reservoir_status | 6 | 6 | 0 | not applicable (not attempted) |
| gold_documents | 11 | 11 | 0 | not applicable |
| gold_operational_risk_inputs | 17382 (6 domains combined) | 1678 geography×date cells | 0 | resolved-only by construction |

`gold_operational_risk_inputs` signal coverage across its 1678 cells: rainfall_observation 660, disaster_event 560, air_quality_observation 351, gauge_observation 93, hazard_alert 15, weather_observation 27 — every other signal on every other cell is `None`, not `0`.

`gold_gauge_daily`'s 3686 output rows from 14,500 input observations (3593/3686 = 97.5% unresolved) is the same real, pre-existing PDMA station-identity gap Task 10/19/20 already documented — stations like "Tarbela"/"Chashma" are facility names, not administrative units, and are correctly left unresolved here too, not guessed at.

## Idempotency

`scripts/gold/run_gold.py` run twice against the same canonical input produced byte-identical output for every dataset file and every summary file (verified via sha256 comparison during this task).

## Spark/Delta status

**NOT executed.** pyspark remains uninstalled in this environment (unchanged since Task 16A). Every Gold transform in `pipeline/gold/transforms.py` is a plain `list[dict] -> list[dict]` function with no Spark/pandas dependency, so it is directly portable into a future Spark transform once pyspark is available — this was not re-verified by actually installing it.

## Known limitations

- `gold_gauge_daily` geography resolution is weak (93/3686 resolved), inherited directly from the PDMA gauge station-naming gap documented in Tasks 10/19/20 — not solved here, by design (no geography invention).
- Task 17-legacy domains (weather/rainfall/gauge/disaster_event, legacy half of hazard_alert) still lack `source_file`/`sha256` raw-artifact provenance (Task 20's documented gap) — Gold inherits this from Silver unchanged.
- `gold_documents` has a publication/effective date for only a minority of documents (most FFC/NDMC PDFs state no reliable publication date in their text) — stays `None`, not fabricated.
- No Gold table was written to PostgreSQL — Gold currently exists only as local JSONL/JSON files under `data/analytics/gold/`; wiring it into the operational database is a later task.
