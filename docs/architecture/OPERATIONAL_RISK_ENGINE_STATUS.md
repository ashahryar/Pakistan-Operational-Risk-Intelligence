# Operational risk engine foundation — status (Task 23)

This is the first auditable operational-risk computation layer, **not a production risk model**. It produces transparent, deterministic, explainable per-`admin_unit_id × date` signals with evidence-based partial coverage. **It does not produce a Pakistan-wide risk score, and no numeric `risk_score` is computed (the field is always null in v1.0.0).**

## Pipeline

```
Gold datasets (data/analytics/gold/datasets)
  → pipeline/risk/signals.py        resolved-geography signal extraction (+ unresolved kept separately)
  → pipeline/risk/normalization.py  percentile rank vs the unit's own STRICTLY-PRIOR history
  → pipeline/risk/aggregation.py    status / basis / confidence (config-driven, PROVISIONAL cut points)
  → pipeline/risk/explanations.py   machine-readable drivers built only from contributing signals
  → pipeline/risk/engine.py         gold_operational_risk rows, coverage, reservoir context
```
Configuration: `config/risk_engine.yaml` (engine_version 1.0.0, calculation_version `risk-engine-1.0.0`). Every row carries `calculation_version`, `engine_version`, `threshold_status=PROVISIONAL`. Scripts: `scripts/risk/run_risk_engine.py`, `scripts/risk/validate_risk_output.py`.

## Status and basis semantics

`risk_status`: `NO_SIGNAL`, `INSUFFICIENT_DATA`, `LOW`, `MODERATE`, `HIGH`, `CRITICAL`. `risk_basis` says *how*: `OBSERVED_SIGNAL_ONLY` (signals seen but none can responsibly drive a status → status `INSUFFICIENT_DATA`), `THRESHOLD_BASED` (one normalized domain), `MULTI_SIGNAL` (≥2 normalized domains), `ALERT_DRIVEN` (a source-published alert severity drove it), `INSUFFICIENT_DATA`.

Nothing here is an authoritative threshold. **PROVISIONAL, relative-to-own-history** mechanisms only:
- Numeric domains (rainfall, weather temperature, gauge discharge, AQI): percentile rank of the value among that same unit's *earlier* observations (`min_history_observations` to normalize; **≥30 prior observations** (`min_history_for_status`) before a normalized value may drive a status, because a percentile over *n* points has resolution 1/*n* and a 0.98 cut point is meaningless for tiny *n*). Cut points MODERATE 0.75 / HIGH 0.90 / CRITICAL 0.98.
- Alerts: only a severity label the source itself published (`Very Heavy`→HIGH, `Heavy`→MODERATE, provisional map). Missing severity stays unmapped (`weather_outlook` alerts, campaign colours such as `green`) — preserved, never invented.
- Disasters: trailing-30-day count of resolved event records, observed-only (routine sitrep rows have no defensible baseline; casualties are **not** converted into a current risk number).
- Documents: never create numeric risk (RAG/context only). Reservoirs: not attributable to an admin unit → written to `reservoir_context.json`, never forced into a row.

## Temporal and missing-data rules

A row for date T uses only observations dated ≤ T; baselines use dates strictly < T (the cell's own value is never its own baseline). Alerts with no validity window are active only on their issue date (`alert_default_extra_active_days: 0`) — Task 21/22 treated them as active forever, which is unsupported. Missing ≠ zero: a null value creates no observation; an observed 0 stays 0; an absent alert/event is *missing*, never "no event" (event/alert feeds have no completeness guarantee). Test `test_removing_future_events_does_not_change_an_earlier_row` caught a real leak during development (a disaster signal's `source_record_id` listed *future* event ids) — fixed.

## Geography

Only `resolution_status == resolved` rows with an `admin_unit_id` become signals; unresolved/ambiguous rows are preserved unmapped in `unresolved_signals.jsonl`. No spreading: a province-level alert/event attaches only to that province's unit, never to districts. Admin units with a documented caveat (`scripts/geo/canonical_data.py`: Mangla, Fort Munro, Kamra, Joharabad) are reported but never drive a status (`GEOGRAPHY_CAVEAT`). This matters in practice: **the only resolved gauge station is "Mangla", mapped to the caveated "Mangla" district**, so gauge contributes no status at all today.

## Real-data results (local Gold, 2026-10-02 run)

1677 rows · 62 distinct admin units (level 2: 1117 rows, level 1: 560) · dates 2025-03-03 → 2026-09-16 · `risk_score` populated on 0 rows.

| Status | Rows |
|---|---:|
| INSUFFICIENT_DATA (basis OBSERVED_SIGNAL_ONLY) | 1312 |
| LOW | 318 |
| MODERATE | 21 |
| HIGH | 20 (13 threshold-based, 7 alert-driven) |
| CRITICAL | 6 |

Confidence: INSUFFICIENT 1312, MEDIUM 365, HIGH 0, LOW 0. ML forecast attached: 0 rows (117 rows blocked by the Mangla caveat, 1560 had no eligible prediction).

| Domain | Source obs. | Resolved | Resolved % | Resolved geographies | Dates | Range |
|---|---:|---:|---:|---:|---:|---|
| rainfall | 869 | 660 | 75.95 | 42 | 78 | 2025-03-03 → 2026-07-14 |
| gauge | 3686 | 93 | **2.52** | **1** | 93 | 2026-06-15 → 2026-09-15 |
| weather | 39 | 27 | 69.23 | 27 | **1** | 2026-08-12 |
| air_quality | 352 | 352 | 100 | **1 (Lahore)** | 351 | 2025-10-01 → 2026-09-16 |
| hazard_alert | 38 | 36 | 94.74 | 7 | 5 | 2026-06-27 → 2026-09-02 |
| disaster_event | 1543 | 1543 | 100 | 7 (provinces) | 80 | 2026-06-27 → 2026-09-16 |
| reservoir | 6 | 0 | — | — | — | not attributable |

Unresolved signal records preserved: 3629 (gauge 3406, rainfall 209, weather 12, hazard_alert 2). Per-row signal states: weather never normalizable (single date), AQI observed only for Lahore, rainfall mostly insufficient history/MISSING, gauge 93 `GEOGRAPHY_CAVEAT` rows.

**Coverage is partial and concentrated:** this is not national coverage — Lahore dominates AQI; weather has one day; gauge geography is ~97.5% unresolved; rainfall and hazard/disaster data are sparse and event-driven.

## ML (Task 22)

Not integrated into any status or score. `ml_fields` only exposes a forecast when the station is a qualifying model station, its geography is resolved and not caveated, and the prediction was made on the cell date (no future/target leakage). In the real data no prediction is eligible (the sole resolved station is caveated). Persistence remains the reference model (`ml_reference_model="persistence"`); Task 22's LinearRegression/RandomForest had negative skill.

## Business-facing signals

Each row exposes `business_signals`: `WEATHER_DISRUPTION_SIGNAL` (max normalized rainfall/temperature), `FLOOD_HYDROLOGY_SIGNAL`, `AIR_QUALITY_SIGNAL`, `ACTIVE_HAZARD_SIGNAL` (presence + source severity labels), `RECENT_DISASTER_SIGNAL` (records in window), `DATA_CONFIDENCE`. They are interpretable inputs, not predictions of delay, loss, closure or claims.

## Spark/Databricks, database, AWS

Pure Python/local files; no pyspark, no PostgreSQL write (one read-only `geo.admin_unit` lookup for labels), no AWS.

## Known limitations

No numeric score (no evidence-based weights); thresholds are provisional; most rows cannot support a status; gauge risk effectively unavailable; AQI is Lahore-only; weather has no history; rainfall baselines use prior *observed* days only (sparse); per-row `generated_at` is intentionally omitted (a wall-clock value would break byte-identical reruns; the version of the computation is carried by `calculation_version` instead); no per-row `geography_resolution_pct` (every contributing signal is resolved by construction — unresolved volume is in the coverage matrix and `unresolved_signals.jsonl`); `reservoir_signal` is not a row field because reservoirs cannot be attributed to a unit.
