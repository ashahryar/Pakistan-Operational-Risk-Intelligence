# Canonical → Bronze → Silver lakehouse boundary — status (Task 20)

Task 20 hardens and validates the existing Task 17–19 canonical layer and Task 18 Bronze/Silver boundary against real data. It does not add Gold, ML, RAG, FastAPI, dashboard, or Airflow production wiring.

## Supported domains

The authoritative registry is `pipeline/canonical/domain_registry.py::DOMAIN_REGISTRY`, cross-checked by `assert_registry_matches_contracts()` against `pipeline/canonical/contracts.py::DOMAINS`, `databricks/src/common/schemas.py::DOMAIN_SCHEMAS`, and `databricks/src/silver/canonical_silver.py`'s `_TIMESTAMP_COLUMNS`/`_REQUIRED_NON_NULL_ANY` — a test (`tests/canonical/test_bronze_silver_local_validation.py::test_domain_registry_matches_contracts_bronze_and_silver_definitions`) fails if any of the three drift apart.

| Domain | Source adapters | Required timestamp | Geography |
|---|---|---|---|
| `weather_observation` | `adapt_pmd_daily` | `observed_at` | yes (DISTRICTS, via city) |
| `rainfall_observation` | `adapt_pdma_rainfall` | `observed_at` | yes (DISTRICTS, via station) |
| `gauge_observation` | `adapt_pdma_gauge` | `observed_at` | yes (DISTRICTS, via station) |
| `disaster_event` | `adapt_ndma` | `event_date` | yes (PROVINCES) |
| `hazard_alert` | `adapt_pmd_alerts`, `adapt_pmd_weekly`, `adapt_suparco_campaigns`, `adapt_glof_alerts` | `issued_at` | partial (province-level where the source states one) |
| `air_quality_observation` | `adapt_epa_stations`, `adapt_epa_calendar` | `observed_at` | yes (DISTRICTS) |
| `reservoir_observation` | `adapt_ffc_reservoir` | `observed_at` | **not attempted by design** — the reservoir name "Mangla" would otherwise false-match the Task 10 district entry "Mangla" |
| `document` | `adapt_documents` | none (contracts.py intentionally requires no single timestamp) | not attempted — documents, not administrative observations |

## Bronze contract

Near-verbatim copy of the canonical record. Deduplication identity: `(domain, source, source_record_id)`, latest `ingestion_timestamp` wins — the same `BRONZE_KEY_COLUMNS`/`BRONZE_ORDER_BY` the Spark module already defined in Task 18, reused unchanged. No business logic, no risk scoring, no aggregation. Bronze-stage validation only checks the four `contracts.REQUIRED` fields plus the four core provenance fields — not domain typing (that's Silver's job).

## Silver contract

Typed timestamps (ISO/date strings → real timestamp columns, never a fabricated timezone or midnight); a not-fully-null guard on each domain's `required_non_null_any` columns (a row with *some* fields populated is a legitimate partial observation and passes; a row with *all* of them null does not); the same dedup as Bronze. No numeric re-casting beyond what Bronze's explicit schema already types.

## Deduplication rule verified

`(domain, source, source_record_id)` is correct for every current domain — confirmed by running it against the real data (see results below), not assumed. `disaster_event` genuinely has 22 real duplicate `source_record_id`s collapsed from 1565 raw canonical rows to 1543 unique — a real finding from NDMA's own data, not a bug introduced by this task.

## Provenance rule

Every record carries `source`, `source_record_id`, `provenance.{source_organization,source_dataset,parser_version,normalization_version}`, `ingestion_timestamp` — enforced by `contracts.validate_record`. Tier-1 records (air_quality_observation, reservoir_observation, document, and the Tier-1 half of hazard_alert) additionally carry `provenance.{source_file,sha256,retrieved_at}`, because Task 15 built a raw-artifact manifest for them. The Task 17 legacy domains (disaster_event, gauge/rainfall/weather_observation, the legacy half of hazard_alert) do **not** carry `source_file`/`sha256`, because NDMA/PDMA/PMD parsing predates Task 15's manifest system and has no raw-artifact checksum to attach — this is a real, by-design gap, not an oversight, and is visible in `data/analytics/lakehouse/lakehouse_quality_report.json`.

## Timestamp rule

`normalize_timestamp()` (fixed in this task — see below) never invents a timezone or a midnight time for a date-only source value: `"2026-09-17"` stays `"2026-09-17"`, not `"2026-09-17T00:00:00"`.

## Null rule

A missing numeric value is always `None`, never `0` or a fabricated default — verified against the real EPA AQI, PDMA gauge, and PDMA rainfall data, where this actually occurs.

## Local validation status (pyspark NOT installed)

`pyspark` is confirmed not installed in this environment (unchanged since Task 16A). **Spark/Delta code was NOT executed.** `databricks/src/common/local_validation.py` is a pure-Python stand-in: it imports the real Spark modules' own dedup/typing configuration (`BRONZE_KEY_COLUMNS`, `BRONZE_ORDER_BY`, `_TIMESTAMP_COLUMNS`, `_REQUIRED_NON_NULL_ANY` — plain Python objects, importable without pyspark) and performs the equivalent logical checks. `scripts/lakehouse/validate_lakehouse.py` runs it against every real canonical JSONL file on disk and writes `data/analytics/lakehouse/{bronze_validation_summary,silver_validation_summary,lakehouse_quality_report}.json`. The real Spark code in `databricks/src/{bronze,silver}/` is unchanged and would run unmodified once pyspark is available — this was not re-verified by actually installing it.

## Real-data validation results (this task's run)

| Domain | Sources | Input | Bronze unique | Duplicates removed | Bronze invalid | Silver fully-null | Geography |
|---|---|---:|---:|---:|---:|---:|---|
| `air_quality_observation` | tier1_epa_punjab_aqi | 371 | 371 | 0 | 0 | 0 | 371 resolved |
| `disaster_event` | task17_ndma | 1565 | 1543 | 22 | 0 | 0 | 1565 resolved |
| `document` | tier1_ffc, tier1_pmd_ndmc | 11 | 11 | 0 | 0 | 0 | not attempted |
| `gauge_observation` | task17_pdma | 14500 | 14500 | 0 | 0 | 1203 | 357 resolved, 14143 unresolved |
| `hazard_alert` | task17_pmd_alerts, task17_pmd_weekly, tier1_ffc, tier1_suparco | 38 | 38 | 0 | 0 | 0 | 36 resolved, 2 no-location |
| `rainfall_observation` | task17_pdma | 869 | 869 | 0 | 0 | 0 | 660 resolved, 61 ambiguous, 148 unresolved |
| `reservoir_observation` | tier1_ffc | 6 | 6 | 0 | 0 | 0 | not attempted |
| `weather_observation` | task17_pmd | 39 | 39 | 0 | 0 | 0 | 27 resolved, 12 unresolved |

`gauge_observation`'s 14,143 unresolved is the expected, documented Task 10 outcome: PDMA gauge station names (e.g. "Tarbela", "Chashma") are facility names, not district names, and are correctly left unresolved rather than guessed. Its 1,203 Silver-stage fully-null rows (both `water_level` and `discharge` null) is a real, pre-existing PDMA PDF-extraction gap, consistent with the project's own documented baseline, surfaced here rather than hidden.

Regenerate with:
```
python scripts/parsing/run_task17_canonical.py   # NDMA/PDMA/PMD -> canonical JSONL (new in this task)
python scripts/parsing/tier1/run_tier1.py        # Tier-1 -> canonical JSONL (Task 19)
python scripts/lakehouse/validate_lakehouse.py   # Bronze/Silver local validation
```

## A real bug found and fixed in this task

`pipeline/canonical/adapters.py::adapt_pmd_daily` read `row.get("max_temperature")`, but the real `scripts/parsing/pmd/daily_parser.py` output field is `temperature` — confirmed by running the adapter against the actual `data/parsed/pmd/daily_forecast/latest.json` for the first time (Task 17's own tests only ever used a synthetic fixture with the wrong key name). Every real PMD daily record's `temperature` field was silently `None` until this task. Fixed with a backward-compatible fallback (`row.get("temperature", row.get("max_temperature"))`); `weather_condition` similarly gained a fallback to the real `forecast_day_1` field.

## Known limitations

- Spark/Delta execution itself was not re-verified (pyspark unavailable); only the pure-Python equivalent ran.
- Legacy Task 17 domains lack `source_file`/`sha256` provenance (no raw-artifact manifest exists for them).
- `document` and `reservoir_observation` intentionally skip geography resolution.
- `gauge_observation`'s high unresolved/fully-null rates are real upstream data-quality gaps (PDMA PDF extraction), not something this task fixes — fixing them is Phase-1 loader/parser work, out of scope here.
