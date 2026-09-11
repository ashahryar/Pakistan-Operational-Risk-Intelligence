# Task 9 — Forecasting Baseline: PDMA Gauge Discharge

**Status:** Implemented and verified 2026-09-11. Phase 1 / Task 9 (ADR-0001). Portfolio-grade MVP, not a decision-support system — see Limitations below.

## What this is

A single, classical, chronologically-evaluated baseline forecast: predicted `discharge_cusecs` (river discharge, one report ahead) for PDMA gauge stations, trained on the live `pdma_gauge_readings` table, run standalone (not wired into any DAG).

## Target variable — and why it isn't `current_level_ft`

The Task 9 plan originally proposed forecasting `current_level_ft` (water level, feet), reasoning it would be directly comparable to the table's own `danger_level_ft` threshold. **Live data profiling on 2026-09-11 found this column is effectively constant per station** — e.g. `Marala` reads exactly `11` for all 314 readings across an 81-day span; every checked station had only 2 distinct `current_level_ft` values across its entire history. This is consistent with the already-documented `parse_gauge.py` hard-coded-column defect (the parser extracts a fixed reference/design number from the PDF table rather than the fluctuating daily reading in some report layouts). Training a model to "forecast" a constant would be trivially, meaninglessly perfect — not a real forecast, and not honest to present as one.

`discharge_cusecs`, in the same table, is genuinely time-varying (100–313 distinct values per station across ~315 readings) with physically plausible magnitudes, so the target was switched before any code was written. This was surfaced to and confirmed by the user before proceeding — see the approved plan's §2.

## Dataset, live-confirmed 2026-09-11

- `pdma_gauge_readings`: **15,274 rows** (up from the 9,517 recorded in the 2026-09-01 baseline — the table has grown since), `report_datetime` range **2026-06-15 18:00 → 2026-09-04 12:00** (~81 days).
- **38 (station, river) pairs qualify** under the completeness rule (≥50 non-null-target, non-null-timestamp readings, spanning ≥30 days) — a live, data-driven selection with no station hard-coded in the code. This includes the 18 major-river barrage stations (Chenab/Ravi/Indus/Sutlej/Jhelum) and 20 hill-torrent/nullah monitoring points. The `river` value for the latter group is a known-corrupted aggregate label (`"RAJANPUR HILL TORRENTS"`, `"DG KHAN HILL TORRENTS"`, `"NULLAHS"` — documented pre-existing defect, not introduced or fixed here); the individual `station` names (e.g. `Sori Janobi`, `Pitok`, `Kaha`) are real, distinct monitoring points.
- **11,796 total readings** loaded for these 38 stations; **11,682 rows** remain after lag/rolling-feature computation (114 dropped — the first few chronological readings per station, which can't have 3 prior readings yet).
- Chronological (never random) 70/15/15 split: train `2026-06-17 → 2026-08-11` (8,206 rows), validation `2026-08-11 → 2026-08-22` (1,748 rows), test `2026-08-23 → 2026-09-04` (1,728 rows).

## Model and result — reported honestly, including the negative finding

Two models, both classical (no PyTorch/TensorFlow):

1. **Persistence baseline**: predicted discharge = the station's last reading.
2. **Linear Regression** (scikit-learn): `lag_1`, `lag_2`, `rolling_mean_3` (all leakage-free — computed only from readings strictly before the row being predicted) + a one-hot station dummy.

| Split | Persistence MAE | Persistence RMSE | LinReg MAE | LinReg RMSE |
|---|---:|---:|---:|---:|
| train | 2,195.1 | 8,645.7 | 2,441.4 | 8,302.4 |
| val | 2,148.0 | 6,398.2 | 2,467.4 | 6,610.6 |
| test | 3,408.7 | 16,056.2 | 3,699.7 | 14,820.1 |

**Skill score (test, `1 - linreg_mae/persistence_mae`): −0.085.** The Linear Regression model does **not** beat the persistence baseline on mean absolute error — it is about 8.5% worse. It *does* have a lower RMSE on the test set (14,820 vs 16,056), meaning it's somewhat better at damping the largest errors (likely by regressing toward each station's typical range rather than chasing the last reading's noise), but worse on typical-case absolute error. **This is reported as a genuine finding, not hidden or improved by changing the evaluation after the fact.** For an MVP with only 3 lag-based features and no exogenous drivers (rainfall, upstream propagation, weather), persistence is a strong baseline for a fast-changing series like river discharge, and beating it needs richer features — the clearest, most concrete next step (see Limitations).

## Artifacts and outputs

- Model: `data/models/gauge_discharge_forecast/2026-09-11/model.joblib` (joblib-serialized fitted `LinearRegression` + its feature-column list).
- Metadata: `data/models/gauge_discharge_forecast/2026-09-11/metadata.json` — full station list, feature columns, split ranges/row counts, both models' metrics on all three splits, skill score, scikit-learn version, git commit (null when run inside the Airflow container, since `.git` isn't mounted there — populate by running on the host), generated-at timestamp.
- Predictions: `data/analytics/pdma/gauge_discharge_forecast.json` — 38 records, one forward (next-report) forecast per qualifying station, in the existing `data/analytics/<source>/*.json` house style (flat array of objects, 4-space indent, snake_case). Each record: `station`, `river`, `based_on_report_datetime`, `forecast_for` ("next_report" — a fixed-clock horizon like "+12h" was deliberately not claimed, since actual reporting cadence per station wasn't verified to be perfectly regular), `predicted_discharge_cusecs`, `model_name`, `model_version`, `source`, `generated_at`.
- **No Postgres table was created.** A minimal, generic `ml_predictions` table shape (reusable by any future forecasting target, not gauge-specific) is proposed as a follow-on, not built here:
  ```sql
  CREATE TABLE IF NOT EXISTS ml_predictions (
      id SERIAL PRIMARY KEY,
      model_name TEXT NOT NULL,
      model_version TEXT NOT NULL,
      target_entity TEXT NOT NULL,
      target_variable TEXT NOT NULL,
      prediction_for TIMESTAMP,
      predicted_value REAL,
      source TEXT NOT NULL,
      generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(model_name, model_version, target_entity, prediction_for)
  );
  ```

## A second environment defect found and worked around (not fixed)

`pandas 3.0.5` (already pinned in this image) silently fails to recognize a SQLAlchemy engine/connection as a "SQLAlchemy connectable" when only `SQLAlchemy 1.4.52` is installed (Airflow 2.9.x's own pin, `<2.0`) — `pandas.io.sql.pandasSQL_builder`'s `import_optional_dependency("sqlalchemy")` call silently returns `None` against that version, and `pd.read_sql()` then raises `TypeError: Query must be a string unless using sqlalchemy.` on any parameterized `text()` query. Worked around by querying via `conn.execute()` directly and building the DataFrame by hand (`scripts/forecasting/gauge_discharge_forecast.py::_query_to_dataframe()`), the same pattern `scripts/database/load_pdma.py` already uses for its inserts — no SQLAlchemy/pandas version was changed (upgrading SQLAlchemy is out of scope: it's an Airflow-pinned core dependency, and bumping it risks breaking Airflow itself).

## Tests

`tests/forecasting/` (17 tests, all deterministic, no live DB, no internet):
- `test_features.py` — `build_lag_features()` (lag/rolling correctness, no cross-station leakage, non-mutation) and `chronological_split()` (no leakage, full coverage, rejects invalid split fractions, and a test that explicitly demonstrates a naive positional/random split violates the same ordering guarantee that `chronological_split()` provides — proving the leakage-check tests are not tautological).
- `test_prediction_schema.py` — an end-to-end (minus the database) run of feature-building → model fit → prediction-record construction against a small **real** fixture (10 genuine `Marala`/`CHENAB` readings, read live from the database during this task's own profiling — see `tests/fixtures/README.md` for provenance), asserting the output schema, JSON-serializability, and a fault-injection-style guard that a record with a missing/blank station name is never written to the output.

Fault-injection proof (temporarily broke `build_lag_features`'s `rolling_mean_3` computation, confirmed 2 tests failed with meaningful diffs, reverted, confirmed 17/17 green again) was run and is not a permanent test artifact.

## Limitations (stated plainly)

- **Does not beat the persistence baseline on MAE** (see above) — the honest headline result of this MVP. A richer feature set (rainfall at the same/upstream stations, weather forecast, seasonality) is the clear next step, explicitly out of scope here.
- **Station-identity noise is not resolved**, only filtered around by the completeness threshold — a station renamed slightly between reports would be treated as two shorter series. Proper entity resolution is Phase 2 (geographic foundation), not this task.
- **`river` values for hill-torrent/nullah stations are known-corrupted aggregate labels** (a pre-existing, documented `parse_gauge.py` defect), carried through verbatim into the predictions output — not fabricated or silently cleaned up.
- **No exogenous features** — the model only knows a station's own recent discharge history.
- **Not validated against a real historical flood event.** No operational flood-warning claim is made.
- **Reporting cadence is treated as "next available reading," not a fixed clock horizon** — inter-reading gaps were not verified to be perfectly regular, so `forecast_for` deliberately says `"next_report"` rather than claiming e.g. "+12h".
- **MLflow was not introduced** — a single model, a single target, run locally, doesn't yet justify a tracking server's operational complexity. Revisit if/when multiple models or scheduled retraining exist.
- **No DAG, database table, dashboard, or AWS change was made** — this is a standalone, locally-proven script, per the approved plan's explicit scope.

## Reproduction

```bash
# Read-only live profiling used to select the target/station population:
docker exec airflow_postgres psql -U airflow -d airflow -c "SELECT count(*), min(report_datetime), max(report_datetime) FROM pdma_gauge_readings;"

# Run the full pipeline (read-only DB queries + local file writes only):
docker exec -w /opt/project -e PYTHONPATH=/opt/project airflow_webserver python scripts/forecasting/gauge_discharge_forecast.py

# Run the test suite:
docker exec -w /opt/project -e PYTHONPATH=/opt/project airflow_webserver pytest tests/forecasting/ -v
```
