# ML feature engineering foundation — status (Task 22)

This task builds leakage-safe, reproducible ML features on top of the validated Gold layer (Task 21) and extends, rather than replaces, Task 9's forecasting foundation (`scripts/forecasting/`). **No ML model in this task is claimed production-ready, and no operational risk score exists anywhere in this repository.**

Distinguish three categories everywhere in this document:
- **OBSERVED DATA** — real values from Gold/Silver (e.g. `discharge_avg`, `rainfall_total`).
- **DERIVED FEATURES** — deterministic functions of strictly-historical observed data (e.g. `lag_1`, `rolling_mean_7`).
- **MODEL PREDICTIONS** — the output of a fitted model, evaluated only on a held-out chronological test set it never saw during training.

## Feature registry

`pipeline/ml/feature_registry.py::FEATURE_REGISTRY` — one entry per implemented feature, each with its source dataset/field, transformation, time window, grouping key, leakage rule, and missing-value behavior. Cross-checked by `tests/ml/test_feature_registry.py`.

## Actual temporal frequency (inspected before any feature was written)

| Gold dataset | Real continuity found | Consequence |
|---|---|---|
| `gold_gauge_daily` | **93 consecutive calendar days** (2026-06-15 → 2026-09-15), 41 stations | Daily lags up to 14 days are defensible; implemented |
| `gold_rainfall_daily` | 869 observations over only **78 distinct dates** across a 16-month span — event-driven, not continuous | Lags are **observation-order**, never a calendar-day window |
| `gold_weather_daily` | All 39 records share **one calendar date** | **Zero** temporal features possible — documented, not fabricated |
| `gold_air_quality` (`daily_district`) | **350 consecutive days**, Lahore district only | Daily lags implemented, Lahore only |
| `gold_air_quality` (`station_snapshot`) | 2 records, no history | Availability flag only |
| `gold_hazard_alerts` / `gold_disaster_events` | Event-driven | Count-based features (`active_alert_count`, `recent_event_count_30d`), not lags |

## A second real data-quality finding (this task's own inspection)

Of `gold_gauge_daily`'s 41 stations, **20 have exactly one distinct `discharge_avg` value across their entire history**, and 3 more have zero non-null values — the same class of defect Task 9 found in `current_level_ft` (a near-constant value is not a real forecasting target), now also present in the daily-aggregated discharge for most stations. `scripts/ml/train_gauge_forecast.py` applies a **data-driven** qualifying filter (`>= 10` distinct `discharge_avg` values; no station name hard-coded) — **18 of 41 stations qualify**: Balloki, Chashma, G.S. Wala, Islam, Jassar, Kalabagh, Khanki, Mangla, Marala, Panjnad, Qadirabad, Rasul, Shahdara, Sidhnai, Suleimanki, Tarbela, Taunsa, Trimmu.

## Geography design decision (Step 9)

`gold_gauge_daily` is ~97.5% geography-unresolved (unchanged from Task 20/21 — not fixed here). Joining rainfall/weather/AQI/hazard signals into the gauge model by `admin_unit_id` would require fabricating a station→district link for the overwhelming majority of stations. **The gauge model is therefore station-level and purely autoregressive** (lags/rolling statistics of its own discharge history + station identity) — extending Task 9's own design, not a new architecture. Rainfall/weather/AQI/hazard/disaster features are built and reported as **separate, standalone** feature tables, never silently joined into the gauge model.

## Target and forecast horizons

Primary target: `target_t_plus_1` = next calendar day's `discharge_avg` (reuses Task 9's `discharge_cusecs` concept at Gold's daily grain — a documented grain change, not a silent one; Task 9's original per-report artifact is untouched). `target_t_plus_3`/`target_t_plus_7` are computed as leakage-safe columns and reported via the persistence baseline only (not modeled with LinearRegression/RandomForest in this task, to keep scope controlled — a defensible, documented choice).

## Train / validation / test boundaries (real run, 18 qualifying stations, 1404 complete rows)

| Split | Rows | Date range |
|---|---:|---|
| Train | 990 | 2026-06-29 → 2026-08-22 |
| Validation | 216 | 2026-08-23 → 2026-09-03 |
| Test | 198 | 2026-09-04 → 2026-09-14 |

Global time-percentile cutoffs (never random, never per-station) — reused unchanged from Task 9's `scripts/forecasting/features.py::chronological_split`. No scaler/normalization statistic is computed before the split (none of the three models used here require scaling: tree/linear models on raw lag values).

## Feature counts (real data)

`scripts/ml/run_feature_pipeline.py` output (`data/analytics/ml/feature_summary.json`): gauge 3686 feature rows (41 stations) → 2929 rows complete for `target_t_plus_1`; rainfall 869 rows, 708 with a `rainfall_lag_1`; AQI 350 daily-district rows (2 station-snapshot, no history); hazard/disaster event features: 1085 rows across 155 as-of dates.

## Baseline metrics (test set, t+1, cusecs)

| Model | MAE | RMSE | R² | Skill vs. persistence |
|---|---:|---:|---:|---:|
| Persistence (last value) | 9552.9 | 19755.3 | 0.925 | — (reference) |
| Linear Regression | 11055.1 | 19358.6 | 0.928 | **−0.157** |
| Random Forest (200 trees, depth 12) | 14218.5 | 23558.8 | 0.893 | **−0.488** |

**Honest result: neither ML model beats the persistence baseline on the held-out chronological test set.** This mirrors Task 9's own finding (persistence MAE ≈ 3408.7, LinearRegression MAE ≈ 3699.7, negative skill at the per-report grain) — the same qualitative conclusion holds at the daily Gold grain too, with a different absolute scale because the target and grain differ. Persistence remains the reference model; this is reported as a legitimate scientific result, not hidden or re-run until it looked better.

Persistence-only metrics across horizons (test): t+1 MAE 9552.9 / R² 0.925; t+3 MAE 15969.5 / R² 0.731; t+7 MAE 26619.3 / R² 0.351 — accuracy degrades with horizon length, as expected.

## Feature importance (Random Forest, NOT causal)

Top 5: `lag_1` (0.754), `rolling_mean_14` (0.113), `rolling_min_7` (0.080), `rolling_max_7` (0.011), `lag_2` (0.007). This describes which inputs the fitted Random Forest relied on most to reduce training error — it is a statement about the model, not a causal claim about discharge physics.

## Leakage protections (tested, `tests/ml/test_leakage.py`, 19 tests)

1. A feature at T is unaffected by mutating every value after T.
2. `rolling_mean_3` excludes the current row even when it's an extreme outlier.
3. Chronological split never lets a test-split timestamp precede a train-split timestamp.
4. Feature values for an early row are identical whether or not later rows exist in the input (no global/full-dataset statistic is computed).
5. A hazard alert/disaster event dated after the as-of date is never counted.
6. Duplicate input rows don't multiply or corrupt the unique-date feature computation.
7. Running gauge/rainfall feature generation twice on the same input produces byte-for-byte identical DataFrames (`pandas.testing.assert_frame_equal`).
8. A missing rainfall observation stays `NaN` through every derived lag/rolling column — never `0`.
9. An unresolved gauge station's `admin_unit_id` stays `None`/absent through feature engineering; hazard/disaster features only ever use resolved-geography records.
10. `target_t_plus_1`/`t_plus_3`/`t_plus_7` are registered as targets (not in `GAUGE_FEATURE_COLUMNS`), and `target_t_plus_1` is verified to equal the *next* row's value, never the current row's own `discharge_avg`.

## Artifacts

`data/models/gauge_discharge_forecast/2026-10-01-task22-daily/` — `metadata.json`, `metrics.json`, `predictions.json` (tracked); `model.joblib` (~11MB, gitignored — reproducible by rerunning the training script; Task 9's original 4KB `2026-09-11/` artifact is tracked and **completely untouched**). `data/analytics/ml/{feature_summary,feature_quality_report}.json` (tracked); `gauge_forecast_features.jsonl` (gitignored — large).

## Spark / Databricks status

Not used. Every feature function in `pipeline/ml/features.py` is plain pandas (no pyspark dependency) — consistent with every ML-adjacent module since Task 9.

## Known limitations

- Only 18 of 41 gauge stations have enough genuine discharge variation to train on; the other 23 are excluded and listed explicitly, not silently dropped.
- `gold_weather_daily` currently supports zero temporal features (single-date snapshot) — a real, stated limitation of the current acquisition, not something this task invents around.
- Rainfall/AQI/hazard/disaster feature tables are built and leakage-tested but **not joined into the gauge model** (the Step 9 geography decision above) — they exist as standalone, documented tables for a future task once gauge geography resolution improves or a different (non-gauge) target is chosen.
- `target_t_plus_3`/`target_t_plus_7` are computed but only evaluated via the persistence baseline, not modeled with LinearRegression/RandomForest, in this task.
- No model here is production-ready, and no composite/operational risk score exists.
