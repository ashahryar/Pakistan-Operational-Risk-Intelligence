# ML prediction layer — status (Task 33)

A lightweight, leakage-safe ML prediction layer that sits **beside** the deterministic operational risk engine. It does not replace the engine, does not change any Task 23 threshold or status, and `risk_score` stays null everywhere. Predictions are **forecasts of an observed quantity at a future date** — never a current risk status.

**Honest headline:** one domain had enough history for a defensible experiment (Lahore air quality, 350 consecutive days). At every horizon the machine-learning candidates **did not beat the simple baselines** on both held-out periods, so **no prediction is shipped as ML**: the three stored Lahore predictions are labelled `BASELINE_ONLY`, and the other 75 areas get explicit `INSUFFICIENT_DATA`. Nothing was tuned to change that.

## Relationship to the other layers

```text
Operational Risk Engine  -> current, evidence-based status (authoritative)       risk_context   [RISK_ENGINE]
ML Prediction Layer      -> a future value of an observed quantity               ml_prediction  [ML_MODEL]
RAG                      -> documentary evidence                                documentary_evidence
Intelligence layer       -> shows all three side by side with explicit provenance (never merged)
```

RAG / documents, risk-engine outputs and manually created labels are **not** ML inputs (a test checks that `pipeline/ml` imports nothing from `pipeline.rag`, `pipeline.intelligence`, `pipeline.risk`).

## Which domain, and why (inspected before any model was written)

| Gold dataset | Real history | Geography | Usable for a prediction experiment? |
|---|---|---|---|
| `gold_air_quality` (`daily_district`) | **350 consecutive days**, 2025-10-01 to 2026-09-15, no missing day | resolved to **Lahore (admin unit 30)** | **Yes — selected** |
| `gold_gauge_daily` | 93 days, 41 stations (20 with a constant value) | 97.5 % unresolved (no station→unit link; none is invented) | Station-level only (Task 22, ML did not beat persistence); not unit-keyed |
| `gold_rainfall_daily` | 869 rows over 78 dates, event-driven | station names only | No (not a continuous series) |
| `gold_weather_daily` | a single date | — | No |
| `risk.operational_risk` history | 1,586 rows but almost all `INSUFFICIENT_DATA` | resolved | No (labels would be the engine's own mostly-empty outputs) |

## Target definition

- **Target:** the observed daily air-quality index (`aqi_avg`) of an admin unit, `h` days after the feature cutoff; horizons **1, 3 and 7** days. Regression.
- **Feature cutoff / origin `D`:** the last day whose observation may be used (inclusive). **Target date:** `D + h`. Label = the observation dated exactly `D + h`.
- **Features (all use observations dated ≤ D only):** `lag_0, lag_1, lag_2, lag_6, lag_13`, rolling means over 3/7/14 days ending at D (all days must be observed), `rolling_std_7`, `delta_1`. No calendar/month features (one year of data cannot learn seasonality), no other domain, no documents.
- **Missing data:** the series sits on the full calendar grid; a missing day stays NaN (never interpolated/forward-filled/zero-filled). A row with any NaN feature or a missing label is *not usable* and is counted by reason (`missing_or_insufficient_history`, `target_not_observed`): 4.0 % (h1), 4.6 % (h3), 5.7 % (h7) of candidate rows.
- **Minimum requirements:** ≥ 180 observed days per entity; ≥ 100 train rows and ≥ 20 validation and test rows after the split; the entity's latest observation within 3 days of the dataset's latest date; complete features at the latest origin. Otherwise `INSUFFICIENT_DATA`. `as_of` is the dataset's own latest observation date (2026-09-15), never the wall clock — the data ends before today, so the forecasts are for 2026-09-16 / -18 / -22.

## Temporal split (strict, purged, never random)

70 / 15 / 15 of the sorted unique target dates; each split's labels lie inside its own period and later splits start after the previous period ends; rows straddling a boundary are purged (counted, unused).

| Horizon | Train (target dates, rows) | Validation (rows) | Test (rows) | Purged |
|---|---|---|---|---:|
| 1 d | 2025-10-15 → 2026-06-06 (235) | 2026-06-08 → 2026-07-26 (49) | 2026-07-28 → 2026-09-15 (50) | 2 |
| 3 d | 2025-10-17 → 2026-06-06 (233) | 2026-06-10 → 2026-07-26 (47) | 2026-07-30 → 2026-09-15 (48) | 6 |
| 7 d | 2025-10-21 → 2026-06-07 (230) | 2026-06-15 → 2026-07-27 (43) | 2026-08-04 → 2026-09-15 (43) | 14 |

The test period (late July to mid September, monsoon season) is much cleaner air than the training period (October–June, smog season): a strong level shift that models trained on one year cannot anticipate.

## Models and decision rule

Baselines (no fitting): **persistence** (last value) and **rolling mean of 7 days**; the best baseline is chosen on validation MAE. ML candidates chosen for a small tabular autoregression: ridge (scaler fit on the training split only), a shallow random forest, a small histogram gradient boosting model — fixed hyper-parameters, fixed seed, **no search on the test period**. The best candidate by validation MAE is refit on train + validation and scored **once** on the test period. The ML model is used only if its MAE beats the best baseline on **both** validation and test; otherwise the deployed predictor is the baseline and rows are `BASELINE_ONLY`. MAE is the decision metric (the target is continuous: MAE/RMSE/R², no classification metrics); R² is relative to the evaluated period's own mean and can be negative under a level shift.

## Results (real data; MAE in AQI points)

| Horizon | Best baseline (val / test MAE) | Selected ML model (val / test MAE) | Skill vs baseline (val / test) | Beats on both? | Deployed |
|---|---|---|---|---|---|
| 1 d | persistence (20.71 / 14.10) | ridge (21.20 / 12.67) | −0.024 / +0.101 | **No** (validation worse) | persistence |
| 3 d | rolling mean 7 (27.43 / 16.07) | random forest (30.41 / 18.95) | −0.109 / −0.179 | **No** | rolling mean 7 |
| 7 d | rolling mean 7 (26.95 / 15.95) | random forest (33.23 / 21.02) | −0.233 / −0.317 | **No** | rolling mean 7 |

Test RMSE / R² of the selected model: h1 15.98 / 0.17, h3 23.49 / −0.79, h7 27.32 / −1.59. Candidates' validation MAE: h1 ridge 21.20, forest 22.22, boosting 24.93. The 1-day ridge has a lower test MAE than persistence but not a lower validation MAE, so it is not validated; with 50 test rows this is not evidence of a real improvement.

**Stored predictions (`ml.predictions`, 76 areas × 3 horizons = 228 rows): 3 valid `BASELINE_ONLY` (Lahore: 126.0 AQI for 2026-09-16 by persistence; 135.4 for 2026-09-18 and 2026-09-22 by the 7-day mean), 0 `PREDICTED`, 225 `INSUFFICIENT_DATA`** (reason stored per row, e.g. "no air_quality observations exist for this area (0 observed days; at least 180 needed)").

## Leakage protections (tested)

1. Mutating every observation after day D leaves every feature of every row with origin ≤ D unchanged (and the later rows do change, so the test is not vacuous): `test_future_observations_cannot_enter_historical_features`.
2. Features of early rows are identical whether or not later data exists (no global statistic).
3. Labels are exactly the observation at D + h and are never a feature; same-day information is limited to the origin day D, which is known by definition.
4. The split is temporal and purged; an assertion detects a random split; each split's labels stay inside its period.
5. Model selection uses validation only: replacing all post-validation values leaves the selected model and validation scores unchanged (only the test score moves).
6. Missing days stay NaN and make dependent rows unusable; stale or incomplete recent data gives `INSUFFICIENT_DATA`.
7. No imports of RAG / documents / risk-engine modules in `pipeline/ml`; unresolved geography is never assigned a unit.

## Storage, API and integration

- Migration `db/migrations/0033_ml_predictions.{up,down}.sql` (additive, separate `ml` schema; `down` removes only it): `ml.model_runs` (run id derived from a data fingerprint so re-running is idempotent; periods, counts, metrics, versions, cutoffs) and `ml.predictions` with contract checks (`INSUFFICIENT_DATA ⇔ prediction IS NULL`, `feature_cutoff < prediction_date`). A restore-verified `pg_dump` (outside the repo, restored into the new scratch database `pori_t33_restore_check`) was taken before applying; the migration was proven idempotent and reversible on that copy first.
- Pipeline: `scripts/ml/run_prediction_pipeline.py [--load]` (artifacts in `data/models/risk_prediction/<run id>/`, report `data/analytics/ml/prediction_evaluation_report.json`). Code: `pipeline/ml/{contracts,dataset,splitting,models,evaluation,runner,registry}.py` (pandas + scikit-learn only; no MLflow or external registry).
- **API (read-only):** `GET /api/v1/ml/predictions?admin_unit_id=&date=&horizon=&status=&include_insufficient=&limit=` and `GET /api/v1/ml/models`. Row contract: `admin_unit_id, entity_type, entity_id, prediction_date, horizon_days, target, unit, prediction, status (PREDICTED | BASELINE_ONLY | INSUFFICIENT_DATA), reason, model_name, model_version, model_type (ml | baseline | none), training_cutoff, feature_cutoff, model_run_id, provenance {provenance: ML_MODEL, validated_against_baseline, evaluation, note}`. No match gives an explicit empty response. POST etc. answer 405.
- **Intelligence:** `/api/v1/intelligence/ask` gains `ml_prediction` — `null` unless a valid (non-`INSUFFICIENT_DATA`) prediction exists for the area; never part of `risk_context`. With a provider, the model receives it as a third labelled block (`[ml_prediction]`) and the validator rejects: a forecast described as current/observed or as a risk status/level/score, a sentence without forecast framing, mixing with another citation, or an `[ml_prediction]` citation with no forecast. These are wording heuristics, not proof of faithfulness.
- **Dashboard:** the Intelligence page has an *ML Forecast (not a current risk status)* section: horizon, forecast date, value, status, model/version, training cutoff, feature cutoff, a clear "NOT a validated ML model" caption for baseline rows, and the `INSUFFICIENT_DATA` state with its reason. No probability/confidence is shown because the models provide no calibrated one; no decorative chart.

## Limitations

One domain, one geography (Lahore), one year of data: no seasonality can be learned and the test period is a different regime. The baseline forecasts are real but trivially simple (and their data ends 2026-09-15). No calibrated uncertainty. Gauge discharge, rainfall and weather are not unit-level predictable until their geography/continuity improves (no station→unit mapping was invented). The `BASELINE_ONLY` forecast is not evidence of an ML capability. Real LLM behaviour with the new block is untested (no credential).

## Next steps

Accumulate more history (a second year of air quality) and revisit the same pipeline unchanged; improve gauge geography (a real, evidenced station→unit crosswalk) before any unit-level hydrology forecast; add calibrated intervals (e.g. conformal) only when a model validates; then evaluate the LLM explanation of `[ml_prediction]` once a provider is configured.
